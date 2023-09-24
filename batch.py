import os
from glob import glob
import ffmpeg
import subprocess
import shutil
from time import time

SCALE = 2

EXTRACT_IMAGE_FOLDER = './videos/tmp_frames'
OUTPUT_IMAGE_FOLDER = './videos/out_frames'
INPUT_VIDEOS_FOLDER = './videos/input_videos'
OUTPUT_VIDEOS_FOLDER = './videos/output_videos'
LOG_FOLDER = './videos/logs'

ESTIMATE_DECODE_SPEED = 350
ESTIMATE_UPSCALE_SPEED = 11
ESTIMATE_REBUILD_SPEED = 22



# 初始化帧工作目录
def refresh_frames_folder():
    for path in [EXTRACT_IMAGE_FOLDER, OUTPUT_IMAGE_FOLDER]:
        if os.path.exists(path):
            shutil.rmtree(path)
        os.makedirs(path, exist_ok=True)

def estimate_time(input_videos):
    input_videos_unprocessed = []
    for input_video in input_videos:
        input_video_fullname = input_video.split('\\')[-1]
        input_video_name = os.path.splitext(input_video_fullname)[0]
        output_video_fullname = f'{input_video_name}_4x.mp4'
        output_path = input_video.replace(INPUT_VIDEOS_FOLDER, OUTPUT_VIDEOS_FOLDER).replace(input_video_fullname, output_video_fullname)
        if not os.path.exists(output_path):
            input_videos_unprocessed.append(input_video)
    
    total_time_second = 0
    for input_video in input_videos_unprocessed:
        info = ffmpeg.probe(input_video)
        video_info_dict = next(c for c in info['streams']
                         if c['codec_type'] == 'video')
        nb_frames = int(video_info_dict['nb_frames'])
        estimate_decode_time = nb_frames / ESTIMATE_DECODE_SPEED
        estimate_upscale_time = nb_frames / ESTIMATE_UPSCALE_SPEED
        estimate_rebuild_time = nb_frames / ESTIMATE_REBUILD_SPEED
        total_time_second = total_time_second + estimate_decode_time + estimate_upscale_time + estimate_rebuild_time
    total_h = total_time_second // 3600
    total_m = (total_time_second % 3600) // 60
    total_s = round(total_time_second % 60, 2)
    print(f'====== 总览预估 =====')
    print(f'总视频数: {len(input_videos)}')
    print(f'已处理视频数: {len(input_videos) - len(input_videos_unprocessed)}')
    print(f'待处理视频数: {len(input_videos_unprocessed)}')
    print(f'预估时间: {total_h} 小时 {total_m} 分 {total_s} 秒\n\n')
        


if __name__ == '__main__':
    if os.path.exists(LOG_FOLDER):
        shutil.rmtree(LOG_FOLDER)
    for path in [INPUT_VIDEOS_FOLDER, OUTPUT_VIDEOS_FOLDER, LOG_FOLDER]:
        os.makedirs(path, exist_ok=True)

    input_videos = []
    for (folder, sub_folders, files) in os.walk(INPUT_VIDEOS_FOLDER):
        for file in files:
            input_videos.append(os.path.join(folder, file))
            
    estimate_time(input_videos)

    total_processing_time = 0
    processed_videos_num = 0
    for index, input_video in enumerate(input_videos):
        tv0 = int(time())
        refresh_frames_folder()
        print(f'====== 处理进度 [{index + 1}/{len(input_videos)}] =====')
        input_video_fullname = input_video.split('\\')[-1]
        input_video_name = os.path.splitext(input_video_fullname)[0]
        output_video_fullname = f'{input_video_name}_4x.mp4'
        output_path = input_video.replace(INPUT_VIDEOS_FOLDER, OUTPUT_VIDEOS_FOLDER).replace(input_video_fullname, output_video_fullname)
        # 获取视频流基本信息
        info = ffmpeg.probe(input_video)
        video_info_dict = next(c for c in info['streams']
                         if c['codec_type'] == 'video')
        video_w = video_info_dict['width']
        video_h = video_info_dict['height']
        frame_rate = round(eval(video_info_dict['r_frame_rate']), 2)
        nb_frames = int(video_info_dict['nb_frames'])
        bit_rate = int(video_info_dict['bit_rate'])
        # 判断是否存在音频流
        audio_exists = len([c for c in info['streams'] if c['codec_type'] == 'audio']) > 0
        

        print(f"""
        视频名称: {input_video_fullname}
        width: {video_w}
        height: {video_h}
        frame_rate: {frame_rate}
        audio_exists: {audio_exists}
        nb_frames: {nb_frames}
        """)

        if os.path.exists(output_path):
            print(f'输出文件已存在: {output_path}\n\n\n')
            continue

        time_extract_start = time()
        extract_frames_cmd = f'ffmpeg -i \"{input_video}\" -qscale:v 1 -qmin 1 -qmax 1 -vsync 0 {EXTRACT_IMAGE_FOLDER}/frame%08d.jpg'
        print(f'开始解帧，指令: {extract_frames_cmd}')
        p = subprocess.Popen(
            extract_frames_cmd,
            stderr=subprocess.STDOUT,
            stdout=open(f'{LOG_FOLDER}/{output_video_fullname}_extract.log', 'a'))
        p.wait()
        time_extract_end = time()
        time_consumption = time_extract_end - time_extract_start
        print(f'解帧完成, 用时 {round(time_consumption, 2)} 秒, 速度 {round(nb_frames / time_consumption, 2)} fps')

        time_upsampling_start = time()
        upsampling_cmd = f'.\\realesrgan-ncnn-vulkan.exe -i {EXTRACT_IMAGE_FOLDER} -o {OUTPUT_IMAGE_FOLDER} -n realesr-animevideov3 -s {SCALE} -f jpg'
        print(f'开始超分，指令: {upsampling_cmd}')
        p = subprocess.Popen(
            upsampling_cmd,
            stderr=subprocess.STDOUT,
            stdout=subprocess.DEVNULL)
        p.wait()
        time_upsampling_end = time()
        time_consumption = time_upsampling_end - time_upsampling_start
        print(f'超分完成, 用时 {round(time_consumption, 2)} 秒, 速度 {round(nb_frames / time_consumption, 2)} fps')

        time_rebuild_start = time()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        # 注意，无音频流的不能使用 "-map 1:a:0" 来拷贝原视频音频流，否则报错
        # -c:v hevc -b:v {bit_rate} 使用显卡硬件加速 H265 编码，维持原有码率，在不降低质量的前提下提速约 30%
        rebuild_video_cmd = f'ffmpeg -r {frame_rate} -f image2 -i {OUTPUT_IMAGE_FOLDER}/frame%08d.jpg -i \"{input_video}\" -map 0:v:0 {"-map 1:a:0" if audio_exists else ""} -c:a copy -c:v hevc -b:v {bit_rate} -r {frame_rate} -pix_fmt yuv420p \"{output_path}\" -y'
        print(f'开始合成，指令: {rebuild_video_cmd}')
        p = subprocess.Popen(
            rebuild_video_cmd,
            stderr=subprocess.STDOUT,
            stdout=open(f'{LOG_FOLDER}/{output_video_fullname}_rebuild.log', 'a'))
        p.wait()
        time_rebuild_end = time()
        time_consumption = time_rebuild_end - time_rebuild_start
        print(f'合成完成, 用时 {round(time_consumption, 2)} 秒, 速度 {round(nb_frames / time_consumption, 2)} fps')

        print(f'输出视频: {output_path}')
        processed_videos_num += 1
        
        tv1 = int(time())
        print(f'该视频耗时 {tv1 - tv0} 秒')
        total_processing_time = total_processing_time + (tv1 - tv0)
        total_h = total_processing_time // 3600
        total_m = (total_processing_time % 3600) // 60
        total_s = round(total_processing_time % 60, 2)
        print(f'累计耗时 {total_h} 小时 {total_m} 分 {total_s} 秒')
        avg_processing_time = total_processing_time / (processed_videos_num)
        print(f'平均单个视频耗时 {avg_processing_time} 秒')
        predicted_time = (len(input_videos) - index - 1) * avg_processing_time
        predicted_h = predicted_time // 3600
        predicted_m = (predicted_time % 3600) // 60
        predicted_s = round(predicted_time % 60, 2)
        print(f'预估剩余 {predicted_h} 小时 {predicted_m} 分 {predicted_s} 秒\n\n\n')
    refresh_frames_folder()
        
"""
index : 0
codec_name : h264
codec_long_name : H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10
profile : High
codec_type : video
codec_tag_string : avc1
codec_tag : 0x31637661
width : 640
height : 480
coded_width : 640
coded_height : 480
closed_captions : 0
film_grain : 0
has_b_frames : 2
sample_aspect_ratio : 1:1
display_aspect_ratio : 4:3
pix_fmt : yuv420p
level : 30
chroma_location : left
field_order : progressive
refs : 1
is_avc : true
nal_length_size : 4
id : 0x1
r_frame_rate : 1199/50
avg_frame_rate : 1199/50
time_base : 1/19184
start_pts : 0
start_time : 0.000000
duration_ts : 144800
duration : 7.547957
bit_rate : 303518
bits_per_raw_sample : 8
nb_frames : 181
extradata_size : 41
disposition : {'default': 1, 'dub': 0, 'original': 0, 'comment': 0, 'lyrics': 0, 'karaoke': 0, 'forced': 0, 'hearing_impaired': 0, 'visual_impaired': 0, 'clean_effects': 0, 'attached_pic': 0, 'timed_thumbnails': 0, 'captions': 0, 'descriptions': 0, 'metadata': 0, 'dependent': 0, 'still_image': 0}
tags : {'language': 'und', 'handler_name': 'VideoHandler', 'vendor_id': '[0][0][0][0]'}
"""