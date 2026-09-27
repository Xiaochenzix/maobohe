import math
from PIL import Image,ImageTk
class ModelRenderer:
    def __init__(self,library):
        self.library=library;self.model=None;self.current=None;self.last_image=None;self.errors={};self.cache={}
    def load(self,key):
        if key==self.current:return
        with Image.open(self.library.models[key]['path']) as sheet:
            self.model=[sheet.crop((216*i,0,216*(i+1),168)).convert('RGBA') for i in range(6)]
        self.current=key;self.cache={}
    def frame(self,key,state='idle',side='left',phase=0):
        self.load(key)
        index=1 if state=='tap' and side=='left' else 2 if state=='tap' else 3 if state=='sleep' else 4+int(phase%1>=.5) if state=='happy' else 0
        self.last_image=self.model[index];return self.last_image
    def draw(self,canvas,cx,cy,scale,phase,state,side,key):
        canvas.delete('cat')
        try:
            frame=self.frame(key,state,side,phase)
            size=(round(scale*54),round(scale*42));token=(id(frame),size,canvas.cget('bg'))
            if token not in self.cache:
                image=Image.new('RGBA',size,canvas.cget('bg'))
                image.alpha_composite(frame.resize(size,Image.Resampling.LANCZOS))
                self.cache[token]=ImageTk.PhotoImage(image.convert('RGB'),master=canvas)
            canvas._live_model_photo=self.cache[token]
            canvas.create_image(cx,cy+(math.sin(phase)*1.5 if state=='idle' else 0),image=canvas._live_model_photo,tags='cat')
        except Exception as error:
            self.errors[key]=str(error)
            canvas.create_text(cx,cy,text='造型加载失败',tags='cat')
    def unload(self):self.model=None;self.current=None;self.last_image=None;self.cache={}
    def close(self):self.unload()
