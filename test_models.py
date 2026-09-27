import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
from model_library import ModelLibrary, BUNDLE, safe_path


class ImportTests(unittest.TestCase):
    def test_zip_traversal_and_missing_assets_leave_library_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            lib=ModelLibrary(root)
            original=set(lib.models)
            attack=root/'attack.zip'
            with zipfile.ZipFile(attack,'w') as archive: archive.writestr('../escape.txt','bad')
            with self.assertRaises(ValueError):lib.import_package(attack)
            self.assertFalse((root.parent/'escape.txt').exists())
            with zipfile.ZipFile(attack,'w') as archive:
                archive.writestr('cat.model3.json',json.dumps({'Version':3,'FileReferences':{'Moc':'x.moc3','Textures':['x.png']}}))
            with self.assertRaises(ValueError):lib.import_package(attack)
            self.assertEqual(set(lib.models),original)
            self.assertEqual(list(lib.root.iterdir()),[])

    def test_import_duplicate_persistence_and_external_json_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            lib=ModelLibrary(directory)
            package=next(Path('.qa/community-models').glob('动力*.zip'))
            first=lib.import_package(package)
            second=lib.import_package(package)
            self.assertEqual(first[0]['id'],second[0]['id'])
            again=ModelLibrary(directory)
            self.assertIn(first[0]['id'],again.models)
            self.assertEqual(len([m for m in again.models.values() if m['imported']]),1)
            with self.assertRaises(ValueError):safe_path(Path(directory),'C:/outside.png')
            with self.assertRaises(ValueError):safe_path(Path(directory),'../outside.png')


class RenderingTests(unittest.TestCase):
    def test_all_models_render_and_click_changes_pose(self):
        from model_renderer import ModelRenderer
        from PIL import ImageChops
        with tempfile.TemporaryDirectory() as directory:
            library=ModelLibrary(directory)
            self.assertEqual(len(library.models),13)
            renderer=ModelRenderer(library)
            try:
                for key, model in library.models.items():
                    idle=renderer.frame(key,'idle',phase=0)
                    self.assertIsNotNone(idle.getbbox(),model['name'])
                    left=renderer.frame(key,'tap','left',phase=0)
                    right=renderer.frame(key,'tap','right',phase=0)
                    self.assertIsNotNone(ImageChops.difference(left,right).getbbox(),model['name'])
            finally:renderer.close()

    def test_app_selection_import_and_restart(self):
        import tkinter as tk
        from app import App
        with tempfile.TemporaryDirectory() as directory:
            root=tk.Tk(); root.withdraw()
            app=App(root,directory,preview=True)
            try:
                app.show('petroom')
                self.assertEqual(len(app.model_tree.get_children()),13)
                key=next(iter(app.model_library.models))
                app.model_tree.selection_set(key)
                app.use_selected_model()
                self.assertEqual(app.store.get('pet_style'),key)
                app.start_pet();app.pet.animate();root.update()
                self.assertFalse(app.model_renderer.errors)
                package=next(Path('.qa/community-models').glob('动力*.zip'))
                app.import_model(str(package))
                selected=app.store.get('pet_style')
                self.assertTrue(selected.startswith('model:imported:'))
                self.assertFalse(app.model_renderer.errors)
            finally:app.close()
            root=tk.Tk();root.withdraw()
            app=App(root,directory,preview=True)
            try:
                self.assertEqual(app.store.get('pet_style'),selected)
                self.assertFalse(app.model_renderer.errors)
                app.set_pet_style('经典围巾')
                self.assertIsNone(app.model_renderer.model)
            finally:app.close()


if __name__=='__main__':unittest.main(verbosity=2)
