# -*- encoding:utf-8 -*-
# 2020/2/19   修改人员：monster water
from pydub import AudioSegment
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
importlib.reload(sys)
logging.basicConfig()

base_url = "ws://rtasr.xfyun.cn/v1/ws"
app_id = "8a286bfe"  # 控制台应用里得到   注意是实时语音转写
api_key = "1f74105083654573c1357cbe62a29607"  # 同上
file_path = "audio2.wav"  # 语音文件名 修改成自己的注意路径
MIN_LENGTH = 3
end_tag = "{\"end\": true}"

class Client():
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

    def convert_wav(self, audio_segment):
        return audio_segment.set_frame_rate(16000).set_channels(1).set_sample_width(2)

    def send(self, file_path):
        file_extension = file_path.split('.')[-1].lower()

        if file_extension == 'wav':
            audio = AudioSegment.from_wav(file_path)
            print(f"原始WAV文件信息: 采样率={audio.frame_rate}Hz, 声道数={audio.channels}, 位深={audio.sample_width * 8}bit")

            if audio.frame_rate != 16000 or audio.channels != 1 or audio.sample_width != 2:
                print("正在转换WAV文件格式...")
                audio = self.convert_wav(audio)
                print(f"转换后WAV文件信息: 采样率={audio.frame_rate}Hz, 声道数={audio.channels}, 位深={audio.sample_width * 8}bit")

            # 输出音频时长和文件大小信息
            duration_seconds = len(audio) / 1000.0
            print(f"音频时长: {duration_seconds:.2f} 秒")

            # 将音频数据转换为字节流
            buffer = io.BytesIO()
            audio.export(buffer, format="wav")
            buffer.seek(0)
            file_size = buffer.getbuffer().nbytes
            print(f"文件大小: {file_size} 字节")

            # 跳过WAV文件头
            buffer.seek(44)

            chunk_size = 1280
            chunks_sent = 0
            while True:
                chunk = buffer.read(chunk_size)
                if not chunk:
                    break
                self.ws.send(chunk)
                chunks_sent += 1
                time.sleep(0.04)

            print(f"已发送 {chunks_sent} 个数据块")

        elif file_extension == 'pcm':
            file_object = open(file_path, 'rb')
            try:
                index = 1
                while True:
                    chunk = file_object.read(1280)
                    if not chunk:
                        break
                    self.ws.send(bytes(chunk))

                    index += 1
                    time.sleep(0.04)
            finally:
                # print str(index) + ", read len:" + str(len(chunk)) + ", file tell:" + str(file_object.tell())
                file_object.close()

            self.ws.send(bytes(end_tag.encode('utf-8')))
            print("send end tag success")


        else:
            print(f"不支持的文件格式: {file_extension}")
            return

        self.ws.send(bytes(end_tag.encode('utf-8')))
        print("send end tag success")

    def recv(self):
        try:
            while self.ws.connected:
                result = str(self.ws.recv())
                if len(result) == 0:
                    print("receive result end")
                    break
                result_dict = json.loads(result)
                # print(f"Received action: {result_dict['action']}")

                if result_dict["action"] == "started":
                    print("handshake success, result: " + result)

                if result_dict["action"] == "result":
                    result1 = json.loads(result_dict['data'])
                    # print(f"Raw result data: {result1}")
                    if 'cn' in result1 and 'st' in result1['cn']:
                        st = result1['cn']['st']
                        # print(f"Type: {st.get('type')}")
                        if st.get('type') == '0':  # 检查 'st' 中的 'type'
                            text = ''
                            if 'rt' in st:
                                for rt in st['rt']:
                                    if 'ws' in rt:
                                        text += ''.join(w['cw'][0]['w'] for w in rt['ws'] if 'cw' in w and w['cw'])
                            # print(f"Extracted text: {text}")
                            if len(text) >= MIN_LENGTH:
                                print(f"Final output: {text}")
                            else:
                                print(f"Text too short: {text}")
                        else:
                            pass
                            # print("Skipping non-type-0 result")
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
        self.ws.close()
        print("connection closed")

if __name__ == '__main__':
    client = Client()
    client.send(file_path)