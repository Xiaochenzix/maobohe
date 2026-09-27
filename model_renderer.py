"""Hidden Live2D renderer shared by the preview and desktop canvas."""
import ctypes
import gc
import math
from pathlib import Path
import sys
import time
from PIL import Image, ImageTk


class ModelRenderer:
    WIDTH, HEIGHT = 360, 280

    def __init__(self, library):
        self.library = library
        self.window = None
        self.model = None
        self.current = None
        self.last_time = 0
        self.last_image = None
        self.errors = {}

    def initialize(self):
        if self.window: return
        root = Path(getattr(sys, '_MEIPASS', Path(__file__).parent))
        # Load before GLFW/Live2D so every library uses the same GL implementation.
        self.gl_library = ctypes.WinDLL(str(root / 'assets/runtime/opengl32.dll'))
        import OpenGL.platform
        OpenGL.platform.PLATFORM.GL = self.gl_library
        import glfw
        from OpenGL import GL
        import live2d.v3 as live2d
        self.glfw, self.gl, self.live2d = glfw, GL, live2d
        if not glfw.init(): raise RuntimeError('无法初始化模型渲染器。')
        glfw.window_hint(glfw.VISIBLE, False)
        glfw.window_hint(glfw.DOUBLEBUFFER, False)
        self.window = glfw.create_window(self.WIDTH, self.HEIGHT, 'ModelRenderer', None, None)
        if not self.window:
            glfw.terminate()
            raise RuntimeError('无法创建模型渲染窗口。')
        glfw.make_context_current(self.window)
        live2d.enableLog(False)
        live2d.init()
        live2d.glInit()

    def unload(self):
        if self.model:
            self.glfw.make_context_current(self.window)
            self.model.DestroyRenderer()
            self.model = None
            gc.collect()
        self.current = None
        self.last_image = None

    def load(self, key):
        if key == self.current: return
        if key not in self.library.models: raise ValueError('模型不存在，请重新导入。')
        self.initialize()
        self.unload()
        self.glfw.make_context_current(self.window)
        model = self.live2d.LAppModel()
        model.LoadModelJson(str(self.library.models[key]['path']))
        model.Resize(self.WIDTH, self.HEIGHT)
        model.SetScale(.75)
        model.SetAutoBlinkEnable(True)
        model.SetAutoBreathEnable(True)
        self.parameters = {model.GetParameter(i).id: model.GetParameter(i) for i in range(model.GetParameterCount())}
        self.model = model
        self.current = key
        self.last_time = 0
        self.crop = None

    def frame(self, key, state='idle', side='left', phase=0):
        self.load(key)
        now = time.monotonic()
        token = (state, side)
        if self.last_image is not None and now-self.last_time < .08 and token == self.last_token:
            return self.last_image
        self.glfw.make_context_current(self.window)
        gl, model = self.gl, self.model
        model.Update()
        def put(name, value):
            if name in self.parameters: model.SetParameterValue(name, value)
        tapping = state == 'tap'
        put('CatParamLeftHandDown', int(tapping and side == 'left'))
        put('ParamMouseLeftDown', int(tapping and side == 'left'))
        put('ParamMouseRightDown', int(tapping and side == 'right'))
        put('ParamAngleX', math.sin(phase/3)*3)
        put('ParamMouseX', math.sin(phase/3)*.15)
        if state == 'sleep':
            put('ParamEyeLOpen', 0)
            put('ParamEyeROpen', 0)
        if state == 'happy':
            put('ParamMouthOpenY', .5)
            put('CatParamLeftHandDown', int(phase % 1 < .5))
        else:
            if 'ParamMouthOpenY' in self.parameters: put('ParamMouthOpenY', self.parameters['ParamMouthOpenY'].default)
        gl.glViewport(0, 0, self.WIDTH, self.HEIGHT)
        gl.glClearColor(0, 0, 0, 0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        model.Draw()
        gl.glFinish()
        raw = gl.glReadPixels(0, 0, self.WIDTH, self.HEIGHT, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE)
        image = Image.frombytes('RGBA', (self.WIDTH,self.HEIGHT), raw).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        # Cubism renders premultiplied alpha; convert before Tk compositing.
        import numpy as np
        pixels = np.array(image)
        alpha = pixels[:,:,3:4].astype('float32')
        pixels[:,:,:3] = np.minimum(255, pixels[:,:,:3].astype('float32')*255/np.maximum(alpha,1)).astype('uint8')
        image = Image.fromarray(pixels)
        if self.crop is None:
            box = image.getbbox()
            if not box: raise RuntimeError('模型未生成有效画面。')
            self.crop = (max(0,box[0]-20),max(0,box[1]-20),min(self.WIDTH,box[2]+20),min(self.HEIGHT,box[3]+20))
        image = image.crop(self.crop)
        self.last_image, self.last_time, self.last_token = image, now, token
        return image

    def draw(self, canvas, cx, cy, scale, phase, state, side, key):
        canvas.delete('cat')
        try:
            if key in self.errors: raise RuntimeError(self.errors[key])
            frame = self.frame(key,state,side,phase)
            size = (round(scale*54),round(scale*42))
            from PIL import ImageOps
            frame = ImageOps.contain(frame,size,Image.Resampling.LANCZOS)
            # Composite against the canvas key to prevent dark fringes on the desktop.
            background = Image.new('RGBA',size,canvas.cget('bg'))
            background.alpha_composite(frame,((size[0]-frame.width)//2,(size[1]-frame.height)//2))
            photo = ImageTk.PhotoImage(background.convert('RGB'),master=canvas)
            canvas._live_model_photo = photo
            canvas.create_image(cx,cy,image=photo,tags='cat')
        except Exception as error:
            self.errors[key] = str(error)
            canvas.create_text(cx,cy,text='模型加载失败\n请在模型管理中查看',fill='#97604d',tags='cat')

    def close(self):
        if self.window:
            self.unload()
            self.live2d.glRelease()
            self.live2d.dispose()
            self.glfw.destroy_window(self.window)
            self.glfw.terminate()
            self.window = None
