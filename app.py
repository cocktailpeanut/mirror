import os
import gradio as gr
import requests
from PIL import Image
import base64
import io
import imageio
import json
import socket
url = "http://localhost:8080/completion"
headers = {"Content-Type": "application/json"}
running = False
str = "■"
def run(frame, prompt):
    global running
    global str
    if running:
        return
    running = True
    imageio.imsave('temp.png', frame)
    with open("temp.png", 'rb') as file:
        encoded_string = base64.b64encode(file.read()).decode('utf-8')
    image_data = [{"data": encoded_string, "id": 12}]
    data = {"prompt": "USER:[img-12]" + prompt +".\nASSISTANT:", "n_predict": 128, "image_data": image_data, "stream": True}
    response = requests.post(url, headers=headers, json=data, stream=True)
    with open("output.txt", "a") as write_file:
        write_file.write("---"*10 + "\n\n")
    for chunk in response.iter_content(chunk_size=128):
        with open("output.txt", "a") as write_file:
            content = chunk.decode().strip().split('\n\n')[0]
            try:
                content_split = content.split('data: ')
                if len(content_split) > 1:
                    content_json = json.loads(content_split[1])
                    write_file.write(content_json["content"])
                    print(content_json["content"], end='', flush=True)
                    str = str + content_json["content"]
                    yield str
                write_file.flush()  # Save the file after every chunk
            except json.JSONDecodeError:
                print("JSONDecodeError: Expecting property name enclosed in double quotes")
    running = False
    str = str + "\n\n■"

css = """
#component-5 {
  position: fixed;
  top:0;
  left:0;
  bottom:0;
  right:0;
  padding: 0 !important;
  border-radius: 0 !important;
}
#component-1 {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 400px !important;
  width: auto !important;
  padding: 0;
  background: none !important;
}
#component-10 {
  z-index:1000;
  position: fixed;
  top: 0px;
  right: 0px;
  bottom: 0px;
  border-radius: 0 !important;
  background: none !important;
  border: none !important;
  padding: 0 !important;
  height: 100% !important;
  box-sizing: border-box !important;
  width: 400px !important;
}
#component-10 .form {
  background: none !important;
  border: none !important;
  height: 100% !important;
  box-sizing: border-box !important;
  border-radius: 0 !important;
}
#component-10 .form .container {
  height: 100%;
}
#component-2 {
  background: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  border: none !important;
  height: 100% !important;
  box-sizing: border-box !important;
}
.generating {
  border: none !important;
}
.upload-container {
  width: 100%;
  height: 100%;
}
button {
  display: none !important;
}
textarea {
  background: rgba(0,0,0,0.2) !important;
  color: white !important;
  font-family: monospace !important;
  font-size: 16px !important;
  -webkit-text-fill-color: white !important;
  border: none !important;
  padding: 30px !important;
  height: 100% !important;
  box-sizing: border-box !important;
  border-radius: 0 !important;
}
.progress-text {
  background: none !important;;
  border: none !important;
  color: white !important;
}

video {
  height: auto !important;
}
#component-9 {
  display: none;
}
[data-testid="block-label"] {
  display: none !important;
}
#component-2 [data-testid="block-info"] {
  display: none;
}
[data-testid="block-info"] {
  padding: 10px !important;
  background: rgba(0,0,0,0.2) !important;
  display: block;
  color: white !important;
  margin: 0 !important;
}
"""
demo = gr.Interface(
    run,
    inputs=[
      gr.Image(sources=["webcam"], streaming=True),
      gr.Textbox(value="Describe a person in the image", label="Prompt")
    ],
    outputs=gr.Textbox(label="Output Box"),
    live=True,
    css=css
)
demo.dependencies[0]["show_progress"] = "minimal"
demo.launch()
