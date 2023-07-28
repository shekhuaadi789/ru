import os
import time
import gradio as gr
import cv2
import roop.globals
import roop.metadata
import pathlib
import shutil

from roop.face_helper import extract_face_images
from roop.capturer import get_video_frame, get_video_frame_total, get_image_frame
from roop.utilities import is_image, is_video, create_version_html, get_destfilename_from_path, create_gif_from_video
from settings import Settings

restart_server = False
live_cam_active = False

RECENT_DIRECTORY_SOURCE = None
RECENT_DIRECTORY_TARGET = None
RECENT_DIRECTORY_OUTPUT = None

SELECTION_FACES_DATA = None

last_image = None

input_thumbs = []
target_thumbs = []


IS_INPUT = True
SELECTED_FACE_INDEX = 0

SELECTED_INPUT_FACE_INDEX = 0
SELECTED_TARGET_FACE_INDEX = 0

roop.globals.keep_fps = None
roop.globals.keep_frames = None
roop.globals.skip_audio = None
roop.globals.use_batch = None

input_faces = None
target_faces = None
face_selection = None
fake_cam_image = None

current_cam_image = None
cam_swapping = False

selected_preview_index = 0


def prepare_environment():
    roop.globals.output_path = os.path.abspath(os.path.join(os.getcwd(), "output"))
    os.makedirs(roop.globals.output_path, exist_ok=True)
    os.environ["TEMP"] = os.environ["TMP"] = os.path.abspath(os.path.join(os.getcwd(), "temp"))
    os.makedirs(os.environ["TEMP"], exist_ok=True)
    os.environ["GRADIO_TEMP_DIR"] = os.environ["TEMP"]


def run():
    global input_faces, target_faces, face_selection, fake_cam_image, restart_server, live_cam_active

    prepare_environment()

    available_themes = ["Default", "gradio/glass", "gradio/monochrome", "gradio/seafoam", "gradio/soft", "gstaff/xkcd", "freddyaboulton/dracula_revamped", "ysharma/steampunk"]
    image_formats = ['jpg','png', 'webp']
    video_formats = ['avi','mkv', 'mp4', 'webm']

    server_name = roop.globals.CFG.server_name
    if server_name is None or len(server_name) < 1:
        server_name = None
    server_port = roop.globals.CFG.server_port
    if server_port <= 0:
        server_port = None


    live_cam_active = False
    run_server = True

    while run_server:

        with gr.Blocks(title=f'{roop.metadata.name} {roop.metadata.version}', theme=roop.globals.CFG.selected_theme, css="span {color: var(--block-info-text-color)}") as ui:
            with gr.Row(variant='panel'):
                    gr.Markdown(f"### [{roop.metadata.name} {roop.metadata.version}](https://github.com/C0untFloyd/roop-unleashed)")
                    gr.HTML(create_version_html(), elem_id="versions")
            with gr.Tab("Face Swap"):
                with gr.Row():
                    with gr.Column():
                        input_faces = gr.Gallery(label="Input faces", allow_preview=True, preview=True, height=128, object_fit="scale-down")
                        with gr.Row():
                                bt_remove_selected_input_face = gr.Button("Remove selected")
                                bt_clear_input_faces = gr.Button("Clear all", variant='stop')
                        bt_srcimg = gr.Image(label='Source Face Image', type='filepath', tool=None)
                    with gr.Column():
                        target_faces = gr.Gallery(label="Target faces", allow_preview=True, preview=True, height=128, object_fit="scale-down")
                        with gr.Row():
                                bt_remove_selected_target_face = gr.Button("Remove selected")
                        bt_destfiles = gr.Files(label='Target File(s)', file_count="multiple", elem_id='filelist')
                with gr.Row():
                    with gr.Column(visible=False) as dynamic_face_selection:
                        face_selection = gr.Gallery(label="Detected faces", allow_preview=True, preview=True, height=256, object_fit="scale-down")
                        with gr.Row():
                            bt_faceselect = gr.Button("Use selected face")
                            bt_cancelfaceselect = gr.Button("Cancel")
            
                with gr.Row():
                    with gr.Column():
                        selected_face_detection = gr.Dropdown(["First found", "All faces", "Selected face", "All female", "All male"], value="First found", label="Select face swapping method")
                        max_face_distance = gr.Slider(0.01, 1.0, value=0.65, label="Max Face Similarity Threshold")
                    with gr.Column():
                        roop.globals.keep_fps = gr.Checkbox(label="Keep FPS", value=True)
                        roop.globals.keep_frames = gr.Checkbox(label="Keep Frames", value=False)
                        roop.globals.skip_audio = gr.Checkbox(label="Skip audio", value=False)
                with gr.Row():
                    with gr.Column():
                        selected_enhancer = gr.Dropdown(["None", "Codeformer", "GFPGAN"], value="None", label="Select post-processing")
                        with gr.Accordion(label="Masking", open=True):
                            chk_useclip = gr.Checkbox(label="Use Text to Clip Masking", value=False)
                            clip_text = gr.Textbox(label="List of objects to mask and restore back on fake image", placeholder="hands,hair")
                            
                    with gr.Column():
                        blend_ratio = gr.Slider(0.0, 1.0, value=0.65, label="Original/Enhanced image blend ratio")
                with gr.Row(variant='panel'):
                    with gr.Column():
                        bt_start = gr.Button("Start", variant='primary')
                        with gr.Accordion(label="Results", open=True):
                            resultfiles = gr.Files(label='Processed File(s)', interactive=False)
                            resultimage = gr.Image(type='filepath', interactive=False)
                    with gr.Column():
                        bt_preview = gr.Button("Preview face swap", variant='secondary')
                        with gr.Accordion(label="Preview Original/Fake Frame", open=True):
                            previewimage = gr.Image(label="Preview Image", interactive=False)
                            with gr.Column():
                                preview_frame_num = gr.Slider(0, 0, value=0, label="Frame Number", step=1.0)
                                bt_use_face_from_preview = gr.Button("Use Face from this Frame", variant='primary')
                            

                        
                        
            with gr.Tab("Live Cam"):
                cam_toggle = gr.Checkbox(label='Activate', value=live_cam_active)
                if live_cam_active:
                    with gr.Row():
                        with gr.Column():
                            cam = gr.Webcam(label='Camera', source='webcam', interactive=True, streaming=False)
                        with gr.Column():
                            fake_cam_image = gr.Image(label='Fake Camera Output', interactive=False)


            with gr.Tab("Extras"):
                with gr.Row():
                    files_to_process = gr.Files(label='File(s) to process', file_count="multiple")
                with gr.Row(variant='panel'):
                    with gr.Accordion(label="Post process", open=False):
                        with gr.Column():
                            selected_post_enhancer = gr.Dropdown(["None", "Codeformer", "GFPGAN"], value="None", label="Select post-processing")
                        with gr.Column():
                            gr.Button("Start").click(fn=lambda: gr.Info('Not yet implemented...'))
                with gr.Row(variant='panel'):
                    with gr.Accordion(label="Video/GIF", open=False):
                        gr.Markdown("Extract frames from video")
                        start_extract_frames = gr.Button("Start")
                        gr.Markdown("Create video from image files")
                        gr.Button("Start").click(fn=lambda: gr.Info('Not yet implemented...'))
                        gr.Markdown("Create GIF from video")
                        start_create_gif = gr.Button("Create GIF")
                with gr.Row():
                    extra_files_output = gr.Files(label='Resulting output files', file_count="multiple")
                        
            
            with gr.Tab("Settings"):
                with gr.Row():
                    with gr.Column():
                        themes = gr.Dropdown(available_themes, label="Theme", info="Change needs complete restart", value=roop.globals.CFG.selected_theme)
                    with gr.Column():
                        share_checkbox = gr.Checkbox(label="Public Server", value=roop.globals.CFG.server_share)
                        button_clean_temp = gr.Button("Clean temp folder")
                    with gr.Column():
                        input_server_name = gr.Textbox(label="Server Name", lines=1, info="Leave blank to run locally", value=roop.globals.CFG.server_name)
                    with gr.Column():
                        input_server_port = gr.Number(label="Server Port", precision=0, info="Leave at 0 to use default", value=roop.globals.CFG.server_port)
                with gr.Row():
                    with gr.Column():
                        selected_image_format = gr.Dropdown(image_formats, label="Image Output Format", value=roop.globals.CFG.output_image_format)
                    with gr.Column():
                        selected_video_format = gr.Dropdown(video_formats, label="Video Output Format", value=roop.globals.CFG.output_video_format)
                    with gr.Column():
                        gr.Markdown(' ')
                    
                with gr.Row():
                    button_apply_settings = gr.Button("Apply Settings")
                    button_apply_restart = gr.Button("Restart Server")
                    gr.Markdown(' ')

            input_faces.select(on_select_input_face, None, None)
            bt_remove_selected_input_face.click(fn=remove_selected_input_face, outputs=[input_faces])
            bt_srcimg.change(fn=on_srcimg_changed, show_progress='full', inputs=bt_srcimg, outputs=[dynamic_face_selection, face_selection, input_faces])


            target_faces.select(on_select_target_face, None, None)
            bt_remove_selected_target_face.click(fn=remove_selected_target_face, outputs=[target_faces])

            bt_destfiles.select(fn=on_destfiles_selected, inputs=[bt_destfiles], outputs=[previewimage, preview_frame_num])
            bt_destfiles.clear(fn=on_clear_destfiles, outputs=[target_faces])
            resultfiles.select(fn=on_resultfiles_selected, inputs=[resultfiles], outputs=[resultimage])

            face_selection.select(on_select_face, None, None)
            bt_faceselect.click(fn=on_selected_face, outputs=[dynamic_face_selection, face_selection, input_faces, target_faces])
            bt_clear_input_faces.click(fn=on_clear_input_faces, outputs=[input_faces])

            bt_start.click(fn=start_swap, 
                inputs=[selected_enhancer, selected_face_detection, roop.globals.keep_fps, roop.globals.keep_frames, roop.globals.skip_audio, max_face_distance, blend_ratio, bt_destfiles, chk_useclip, clip_text],
                outputs=[resultfiles, resultimage])
            
            bt_preview.click(fn=start_preview, 
                inputs=[preview_frame_num, selected_enhancer, selected_face_detection, max_face_distance, blend_ratio, bt_destfiles, chk_useclip, clip_text], outputs=[previewimage])
            preview_frame_num.change(fn=on_preview_frame_changed, inputs=[preview_frame_num, bt_destfiles], outputs=[previewimage], show_progress='hidden')
            bt_use_face_from_preview.click(fn=on_use_face_from_selected, show_progress='full', inputs=[bt_destfiles, preview_frame_num], outputs=[dynamic_face_selection, face_selection, target_faces])
            
            # Live Cam
            cam_toggle.change(fn=on_cam_toggle, inputs=[cam_toggle])
            if live_cam_active:
                cam.stream(on_stream_swap_cam, inputs=[cam, selected_enhancer, blend_ratio], outputs=[fake_cam_image], show_progress="hidden")

            # Extras
            start_extract_frames.click(fn=on_extract_frames, inputs=[files_to_process], outputs=[files_to_process, extra_files_output])
            start_create_gif.click(fn=on_create_gif, inputs=[files_to_process], outputs=[files_to_process, extra_files_output])

            # Settings
            button_clean_temp.click(fn=clean_temp, outputs=[bt_srcimg, input_faces, target_faces, bt_destfiles])
            button_apply_settings.click(apply_settings, inputs=[themes, input_server_name, input_server_port, share_checkbox, selected_image_format, selected_video_format])
            button_apply_restart.click(restart)



        restart_server = False
        try:
            ui.queue().launch(inbrowser=True, server_name=server_name, server_port=server_port, share=roop.globals.CFG.server_share, prevent_thread_lock=True, show_error=True)
        except:
            restart_server = True
            run_server = False
        try:
            while restart_server == False:
                time.sleep(5.0)
        except (KeyboardInterrupt, OSError):
            print("Keyboard interruption in main thread... closing server.")
            run_server = False
        ui.close()



def on_srcimg_changed(imgsrc, progress=gr.Progress()):
    global RECENT_DIRECTORY_SOURCE, SELECTION_FACES_DATA, IS_INPUT, input_faces, face_selection, input_thumbs, last_image
    
    IS_INPUT = True

    if imgsrc == None or last_image == imgsrc:
        return gr.Column.update(visible=False), None, input_thumbs
    
    last_image = imgsrc
    
    progress(0, desc="Retrieving faces from image", )      
    source_path = imgsrc
    thumbs = []
    if is_image(source_path):
        roop.globals.source_path = source_path
        RECENT_DIRECTORY_SOURCE = os.path.dirname(roop.globals.source_path)
        SELECTION_FACES_DATA = extract_face_images(roop.globals.source_path,  (False, 0))
        progress(0.5, desc="Retrieving faces from image")      
        for f in SELECTION_FACES_DATA:
            image = convert_to_gradio(f[1])
            thumbs.append(image)
            
    progress(1.0, desc="Retrieving faces from image")      
    if len(thumbs) < 1:
        raise gr.Error('No faces detected!')

    if len(thumbs) == 1:
        roop.globals.SELECTED_FACE_DATA_INPUT = SELECTION_FACES_DATA[0][0]
        input_thumbs.append(thumbs[0])
        return gr.Column.update(visible=False), None, input_thumbs
       
    return gr.Column.update(visible=True), thumbs, gr.Gallery.update(visible=True)
#        bt_srcimg.change( inputs=bt_srcimg, outputs=[bt_srcimg, dynamic_face_selection, face_selection, input_faces])

def on_select_input_face(evt: gr.SelectData):
    global SELECTED_INPUT_FACE_INDEX

    SELECTED_INPUT_FACE_INDEX = evt.index

def remove_selected_input_face():
    global input_thumbs, SELECTED_INPUT_FACE_INDEX

    if len(input_thumbs) > SELECTED_INPUT_FACE_INDEX:
        f = input_thumbs.pop(SELECTED_INPUT_FACE_INDEX)
        del f

    return input_thumbs

def on_select_target_face(evt: gr.SelectData):
    global SELECTED_TARGET_FACE_INDEX

    SELECTED_TARGET_FACE_INDEX = evt.index

def remove_selected_target_face():
    global target_thumbs, SELECTED_TARGET_FACE_INDEX

    if len(target_thumbs) > SELECTED_TARGET_FACE_INDEX:
        f = target_thumbs.pop(SELECTED_TARGET_FACE_INDEX)
        del f
    return target_thumbs





def on_use_face_from_selected(files, frame_num):
    global IS_INPUT, SELECTION_FACES_DATA

    IS_INPUT = False
    thumbs = []
    
    roop.globals.target_path = files[selected_preview_index].name
    if is_image(roop.globals.target_path) and not roop.globals.target_path.lower().endswith(('gif')):
        SELECTION_FACES_DATA = extract_face_images(roop.globals.target_path,  (False, 0))
        if len(SELECTION_FACES_DATA) > 0:
            for f in SELECTION_FACES_DATA:
                image = convert_to_gradio(f[1])
                thumbs.append(image)
        else:
            gr.Info('No faces detected!')
            roop.globals.target_path = None
                
    elif is_video(roop.globals.target_path) or roop.globals.target_path.lower().endswith(('gif')):
        selected_frame = frame_num
        SELECTION_FACES_DATA = extract_face_images(roop.globals.target_path, (True, selected_frame))
        if len(SELECTION_FACES_DATA) > 0:
            for f in SELECTION_FACES_DATA:
                image = convert_to_gradio(f[1])
                thumbs.append(image)
        else:
            gr.Info('No faces detected!')
            roop.globals.target_path = None

    if len(thumbs) == 1:
        roop.globals.SELECTED_FACE_DATA_OUTPUT = SELECTION_FACES_DATA[0][0]
        target_thumbs.append(thumbs[0])
        return gr.Row.update(visible=False), None, target_thumbs

    return gr.Row.update(visible=True), thumbs, gr.Gallery.update(visible=True)



def on_select_face(evt: gr.SelectData):  # SelectData is a subclass of EventData
    global SELECTED_FACE_INDEX
    SELECTED_FACE_INDEX = evt.index
    

def on_selected_face():
    global IS_INPUT, SELECTED_FACE_INDEX, SELECTION_FACES_DATA, input_thumbs, target_thumbs
    
    fd = SELECTION_FACES_DATA[SELECTED_FACE_INDEX]
    image = convert_to_gradio(fd[1])
    if IS_INPUT:
        roop.globals.SELECTED_FACE_DATA_INPUT = fd[0]
        input_thumbs.append(image)
        return gr.Column.update(visible=False), None, input_thumbs, gr.Gallery.update(visible=True)
    else:
        roop.globals.SELECTED_FACE_DATA_OUTPUT = fd[0]
        target_thumbs.append(image)
        return gr.Column.update(visible=False), None, gr.Gallery.update(visible=True), target_thumbs
    
#        bt_faceselect.click(fn=on_selected_face, outputs=[dynamic_face_selection, face_selection, input_faces, target_faces])




def on_preview_frame_changed(frame_num, files):
    filename = files[selected_preview_index].name
    if is_video(filename) or filename.lower().endswith('gif'):
        current_frame = get_video_frame(filename, frame_num)
    else:
        current_frame = get_image_frame(filename)
    return convert_to_gradio(current_frame)
    
    


def on_clear_input_faces():
    global input_thumbs
    
    input_thumbs = []
    roop.globals.SELECTED_FACE_DATA_INPUT = None
    return input_thumbs

def on_clear_destfiles():
    global target_thumbs

    roop.globals.SELECTED_FACE_DATA_OUTPUT = None
    target_thumbs = []
    return target_thumbs    



def translate_swap_mode(dropdown_text):
    if dropdown_text == "Selected face":
        return "selected"
    elif dropdown_text == "First found":
        return "first"
    elif dropdown_text == "All female":
        return "all_female"
    elif dropdown_text == "All male":
        return "all_male"
    
    return "all"
        


def start_swap(enhancer, detection, keep_fps, keep_frames, skip_audio, face_distance, blend_ratio, target_files, use_clip, clip_text):
    from roop.core import batch_process

    if len(target_files) <= 0:
        return None, None
    
    shutil.rmtree(roop.globals.output_path)
    prepare_environment()


    roop.globals.selected_enhancer = enhancer
    roop.globals.target_path = None
    roop.globals.max_face_distance = face_distance
    roop.globals.blend_ratio = blend_ratio
    roop.globals.keep_fps = keep_fps
    roop.globals.keep_frames = keep_frames
    roop.globals.face_swap_mode = translate_swap_mode(detection)
    if use_clip and clip_text is None or len(clip_text) < 1:
        use_clip = False
    
    batch_process([file.name for file in target_files], use_clip, clip_text)
    outdir = pathlib.Path(roop.globals.output_path)
    outfiles = [item for item in outdir.iterdir() if item.is_file()]
    if len(outfiles) > 0:
        return outfiles, outfiles[0]
    return None, None

def start_preview(frame_num, enhancer, detection, face_distance, blend_ratio, target_files, use_clip, clip_text):
    from roop.core import live_swap

    roop.globals.face_swap_mode = translate_swap_mode(detection)
    roop.globals.selected_enhancer = enhancer
    roop.globals.max_face_distance = face_distance
    roop.globals.blend_ratio = blend_ratio
    

    filename = target_files[selected_preview_index].name
    if is_video(filename) or filename.lower().endswith('gif'):
        current_frame = get_video_frame(filename, frame_num)
    elif is_image(filename):
        current_frame = get_image_frame(filename)
    if current_frame is None:
        return None 

    if use_clip and clip_text is None or len(clip_text) < 1:
        use_clip = False
        

    if roop.globals.SELECTED_FACE_DATA_INPUT is not None:
        current_frame = live_swap(current_frame, roop.globals.face_swap_mode, use_clip, clip_text)

    return convert_to_gradio(current_frame)
   
    
def on_destfiles_selected(evt: gr.SelectData, target_files):
    global selected_preview_index

    selected_preview_index = evt.index
    filename = target_files[selected_preview_index].name
    if is_video(filename) or filename.lower().endswith('gif'):
        current_frame = get_video_frame(filename, 0)
        total_frames = get_video_frame_total(filename)
    else:
        current_frame = get_image_frame(filename)
        total_frames = 0
    
    current_frame = convert_to_gradio(current_frame)
    return current_frame, gr.Slider.update(value=0, maximum=total_frames)
    

def on_resultfiles_selected(evt: gr.SelectData, files):
    selected_index = evt.index
    filename = files[selected_index].name
    if is_video(filename) or filename.lower().endswith('gif'):
        current_frame = get_video_frame(filename, 0)
    else:
        current_frame = get_image_frame(filename)
    return convert_to_gradio(current_frame)

    
        
def on_cam_toggle(state):
    global live_cam_active, restart_server

    live_cam_active = state
    gr.Warning('Server will be restarted for this change!')
    restart_server = True


def on_stream_swap_cam(camimage, enhancer, blend_ratio):
    from roop.core import live_swap
    global current_cam_image, cam_counter, cam_swapping, fake_cam_image

    roop.globals.selected_enhancer = enhancer
    roop.globals.blend_ratio = blend_ratio

    if not cam_swapping and roop.globals.SELECTED_FACE_DATA_INPUT is not None:
        cam_swapping = True
        current_cam_image = live_swap(camimage, "all", False, None)
        cam_swapping = False
    
    return current_cam_image


def on_extract_frames(files):
    resultfiles = []
    for tf in files:
        f = tf.name
        resfolder = roop.utilities.extract_frames(f)
        for file in os.listdir(resfolder):
            outfile = os.path.join(resfolder, file)
            if os.path.isfile(outfile):
                resultfiles.append(outfile)
    return None, resultfiles


def on_create_gif(files):
    for tf in files:
        f = tf.name
        gifname = get_destfilename_from_path(f, './output', '.gif')
        create_gif_from_video(f, gifname)
    
    return None, gifname





def clean_temp():
    global input_thumbs, target_thumbs
    
    shutil.rmtree(os.environ["TEMP"])
    prepare_environment()
   
    input_thumbs = []
    roop.globals.SELECTED_FACE_DATA_INPUT = None
    roop.globals.SELECTED_FACE_DATA_OUTPUT = None
    target_thumbs = []
    gr.Info('Temp Files removed')
    return None,None,None,None


def apply_settings(themes, input_server_name, input_server_port, input_server_public, selected_image_format, selected_video_format):
    roop.globals.CFG.selected_theme = themes
    roop.globals.CFG.server_name = input_server_name
    roop.globals.CFG.server_port = input_server_port
    roop.globals.CFG.server_share = input_server_public
    roop.globals.CFG.output_image_format = selected_image_format
    roop.globals.CFG.output_video_format = selected_video_format
    roop.globals.CFG.save()
    gr.Info('Settings saved')

def restart():
    global restart_server
    restart_server = True




# Gradio wants Images in RGB
def convert_to_gradio(image):
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

