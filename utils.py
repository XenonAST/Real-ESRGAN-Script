import time

def timed_log(content):
    cur_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
    print(f'[{cur_time}] {content}')