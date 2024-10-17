# -*- encoding:utf-8 -*-
import io
import sys
import wave
import hashlib
from hashlib import sha1
import hmac
import base64
from socket import *
import json, time, threading
from websocket import create_connection
import websocket
from urllib.parse import quote
import logging
import importlib
from pydub import AudioSegment
import pyaudio
import multiprocessing
import queue
import threading
import requests
importlib.reload(sys)
logging.basicConfig()

base_url = "ws://rtasr.xfyun.cn/v1/ws"
app_id = "8a286bfe"
api_key = "1f74105083654573c1357cbe62a29607"
file_path = "audio2.wav"
MIN_LENGTH = 2
end_tag = "{\"end\": true}"


class PostRequestHandler:
    def __init__(self, url, headers):
        self.url = url
        self.headers = headers
        self.text_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.request_loop)
        self.thread.start()

    def request_loop(self):
        while not self.stop_event.is_set():
            try:
                text = self.text_queue.get(timeout=1)
                self.send_post_request(text)
            except queue.Empty:
                continue

    def send_post_request(self, text):
        data = {
            "query": text,
            "you_name": "同学"
        }
        try:
            response = requests.post(self.url, json=data, headers=self.headers)
            print(f"POST response: {response.json()}")
        except Exception as e:
            print(f"Error sending POST request: {e}")

    def add_text(self, text):
        self.text_queue.put(text)

    def stop(self):
        self.stop_event.set()
        self.thread.join()

class MicrophoneStream:
    def __init__(self, rate=16000, chunk=1280):
        self.rate = rate
        self.chunk = chunk
        self.p = None
        self.stream = None

    def start_stream(self):
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=pyaudio.paInt16,
                                  channels=1,
                                  rate=self.rate,
                                  input=True,
                                  frames_per_buffer=self.chunk)

    def read_audio(self):
        return self.stream.read(self.chunk)

    def stop_stream(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        if self.p:
            self.p.terminate()


def microphone_process(audio_queue):
    mic = MicrophoneStream()
    mic.start_stream()

    try:
        while True:
            data = mic.read_audio()
            audio_queue.put(data)
            time.sleep(0.04)
    except Exception as e:
        print(f"Error in microphone process: {e}")
    finally:
        mic.stop_stream()
        audio_queue.put(None)  # 发送结束信号

class Client:
    def __init__(self):
        # 生成鉴权参数
        ts = str(int(time.time()))
        tmp = app_id + ts
        hl = hashlib.md5()
        hl.update(tmp.encode(encoding='utf-8'))
        h2 = hl.hexdigest()
        apikey = (bytes(api_key.encode('utf-8')))
        h2 = h2.encode('utf-8')
        my_sign = hmac.new(apikey, h2, sha1).digest()
        signa = base64.b64encode(my_sign).decode('utf-8')

        self.ws = create_connection(base_url + "?appid=" + app_id + "&ts=" + ts + "&signa=" + quote(signa))

        self.trecv = threading.Thread(target=self.recv)
        self.trecv.start()
        self.initialize_microphone()
        # 初始化 PostRequestHandler
        url = "http://localhost:8000/chatbot/chat"
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            # ... 其他headers ...
        }
        self.post_handler = PostRequestHandler(url, headers)

        # 新增：麦克风状态控制
        self.microphone_active = True
        self.SILENT_CHUNK = b'\x00\x00' * 640  # 1280 bytes of silence
        self.control_thread = threading.Thread(target=self.remote_control_thread)
        self.control_thread.daemon = True
        self.control_thread.start()


    def initialize_microphone(self):
        self.audio_queue = multiprocessing.Queue()
        self.mic_process = None

    def start_microphone_stream(self):
        self.mic_process = multiprocessing.Process(
            target=microphone_process,
            args=(self.audio_queue,)
        )
        self.mic_process.start()

    def stop_microphone_stream(self):
        if self.mic_process:
            self.mic_process.terminate()
            self.mic_process.join()
        self.audio_queue.put(None)  # 发送结束信号

    def convert_wav(self, audio_segment):
        return audio_segment.set_frame_rate(16000).set_channels(1).set_sample_width(2)

    def send(self, file_path):
        # 保持不变
        pass

    def send_from_microphone(self):
        try:
            while True:
                try:
                    audio_data = self.audio_queue.get(timeout=0.1)
                    if audio_data is None:
                        break
                    if self.microphone_active:
                        self.ws.send(audio_data)
                    else:
                        self.ws.send(self.SILENT_CHUNK)
                except queue.Empty:
                    if not self.microphone_active:
                        self.ws.send(self.SILENT_CHUNK)
                time.sleep(0.04)
            self.ws.send(bytes(end_tag.encode('utf-8')))
            print("Send end tag success")
        except Exception as e:
            print(f"Error sending microphone data: {e}")
        finally:
            self.stop_microphone_stream()

    def start_recognition_from_microphone(self):
        self.start_microphone_stream()
        self.send_from_microphone()


    def recv(self):
        try:
            while self.ws.connected:
                result = str(self.ws.recv())
                if len(result) == 0:
                    print("receive result end")
                    break
                result_dict = json.loads(result)

                if result_dict["action"] == "started":
                    print("handshake success, result: " + result)

                if result_dict["action"] == "result":
                    result1 = json.loads(result_dict['data'])
                    if 'cn' in result1 and 'st' in result1['cn']:
                        st = result1['cn']['st']
                        if st.get('type') == '0':
                            text = ''
                            if 'rt' in st:
                                for rt in st['rt']:
                                    if 'ws' in rt:
                                        text += ''.join(w['cw'][0]['w'] for w in rt['ws'] if 'cw' in w and w['cw'])
                            if len(text) >= MIN_LENGTH:
                                print(f"Final output sent: {text}")
                                self.post_handler.add_text(text)
                            else:
                                print(f"Text too short: {text}")
                    else:
                        print("Missing required keys in result data")

                if result_dict["action"] == "error":
                    print("rtasr error: " + result)
                    self.ws.close()
                    return
        except websocket.WebSocketConnectionClosedException:
            print("receive result end")
        except Exception as e:
            print(f"An error occurred: {str(e)}")

    def close(self):
        self.post_handler.stop()
        self.ws.close()
        print("Connection closed")

    # 新增：麦克风状态控制方法
    def set_microphone_state(self, state):
        if state in ['active', 'deactived']:
            self.microphone_active = (state == 'deactived')#数字人talking状态deactived，mic active
            # print(f"Microphone {'activated' if self.microphone_active else 'deactivated'}")

    # 新增：远程控制线程
    def remote_control_thread(self):
        while True:
            try:
                # self.set_microphone_state('active')
                # response = requests.get("http://your-remote-server.com/microphone-status")
                response = requests.post('http://202.38.78.122:6006/human', json={"text": "", "type": "mic_query"},timeout=0.05)

                if response.status_code == 200:
                    new_state = response.json().get('data', None)
                    if new_state in ['active', 'deactived']:
                        self.set_microphone_state(new_state)
                        # print("set state "+new_state)
                    else:
                        self.set_microphone_state('deactived')
            except requests.RequestException:
                pass  # 请求超时或其他错误，保持当前状态
            # time.sleep(5)
            # print('deactived')
            # self.set_microphone_state('deactive')
            # time.sleep(5)
            # print('actived')

if __name__ == '__main__':
    client = Client()

    # 使用麦克风输入
    client.start_recognition_from_microphone()

    client.close()