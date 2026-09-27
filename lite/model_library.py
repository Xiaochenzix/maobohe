import json,sys
from pathlib import Path
BUNDLE=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'assets/frames'
class ModelLibrary:
    def __init__(self,data_dir):self.refresh()
    def refresh(self):
        self.errors=[]
        self.models=json.loads((BUNDLE/'catalog.json').read_text(encoding='utf8'))
        for key,m in self.models.items():m.update(id=key,path=BUNDLE/m['file'])
    def import_package(self,source):raise ValueError('轻量版仅支持内置造型；导入 Live2D 模型请使用完整版。')
