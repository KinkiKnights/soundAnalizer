import pyaudio
import wave
import time
import threading
import requests
import argparse
import os
from datetime import datetime
from collections import deque

def parse_arguments():
    parser = argparse.ArgumentParser(description='音声録音＆サーバーアップロードプログラム')
    parser.add_argument('--endpoint', type=str, default='up1',
                        choices=['up1', 'up2', 'up3', 'up4'],
                        help='アップロード先エンドポイント (default: up1)')
    parser.add_argument('--server', type=str, default='http://192.168.9.130:5000',
                        help='サーバーアドレス (default: http://192.168.9.130:5000)')
    parser.add_argument('--rate', type=int, default=44100,
                        help='サンプリングレート (default: 44100)')
    parser.add_argument('--segment', type=int, default=6,
                        help='分割秒数 (default: 6)')
    parser.add_argument('--buffer', type=int, default=10,
                        help='リングバッファ保持秒数 (default: 10)')
    return parser.parse_args()

class AudioRecorder:
    def __init__(self, args):
        self.args = args
        self.audio = pyaudio.PyAudio()
        
        # 利用可能なデバイス情報を表示
        self.input_device_index = self.find_input_device()
        
        self.stream = None
        self.recording = False
        self.ring_buffer = deque(maxlen=self.calculate_buffer_size())
        self.lock = threading.Lock()
        self.last_save_time = time.time()
        self.should_save_segment = False # コールバックからメインループへのフラグ
        
        # サーバーURLの構築
        self.server_url = f"{args.server.rstrip('/')}/{args.endpoint}"
        print(f"アップロード先: {self.server_url}")
        print(f"設定: {args.rate}Hz, {args.segment}秒分割, {args.buffer}秒バッファ")
        print(f"使用デバイス: {self.input_device_index}")

    def find_input_device(self):
        """適切な入力デバイスを検索"""
        print("利用可能なオーディオデバイス:")
        for i in range(self.audio.get_device_count()):
            try:
                dev_info = self.audio.get_device_info_by_index(i)
                if dev_info['maxInputChannels'] > 0:  # 入力デバイスのみ
                    print(f"  デバイス {i}: {dev_info['name']}")
                    print(f"    サンプリングレート: {dev_info['defaultSampleRate']}Hz")
                    print(f"    最大入力チャンネル: {dev_info['maxInputChannels']}")
                    # USB Audio Deviceを優先
                    if 'USB Audio Device' in dev_info['name']:
                        print(f"    → 選択: USB Audio Device")
                        print()
                        return i
            except Exception as e:
                print(f"  デバイス {i}: エラー - {e}")
        
        # USB Audio Deviceが見つからない場合は最初の入力デバイスを使用
        for i in range(self.audio.get_device_count()):
            try:
                dev_info = self.audio.get_device_info_by_index(i)
                if dev_info['maxInputChannels'] > 0:
                    print(f"    → 選択: デフォルトデバイス")
                    print()
                    return i
            except:
                continue
        
        print("    → 警告: 入力デバイスが見つかりません")
        print()
        return None

    def calculate_buffer_size(self):
        # バッファサイズ計算 (秒数 * サンプルレート * チャンネル数 * サンプルサイズ)
        return int(self.args.rate * self.args.buffer * 1 * 2)

    def start(self):
        if self.input_device_index is None:
            raise Exception("入力デバイスが見つかりません")
            
        self.recording = True
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.args.rate,
            input=True,
            input_device_index=self.input_device_index,
            frames_per_buffer=1024,
            stream_callback=self.callback
        )
        print("録音を開始しました...")
        self.stream.start_stream()

    def stop(self):
        self.recording = False
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass
        try:
            self.audio.terminate()
        except:
            pass
        print("録音を停止しました")

    def callback(self, in_data, frame_count, time_info, status):
        try:
            with self.lock:
                self.ring_buffer.extend(in_data)
                
                current_time = time.time()
                if current_time - self.last_save_time >= self.args.segment:
                    self.last_save_time = current_time
                    # フラグを設定してメインループで処理
                    self.should_save_segment = True
        except Exception as e:
            print(f"コールバックエラー: {e}")
                
        return (in_data, pyaudio.paContinue)

    def save_segment(self):
        try:
            with self.lock:
                segment_size = int(self.args.rate * self.args.segment * 2)  # 16bit = 2バイト
                if len(self.ring_buffer) < segment_size:
                    return
                    
                segment_data = bytes(list(self.ring_buffer)[-segment_size:])
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"recording_{self.args.endpoint}_{timestamp}.wav"
                
                with wave.open(filename, 'wb') as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
                    wf.setframerate(self.args.rate)
                    wf.writeframes(segment_data)
                
                self.upload_file(filename)
        except Exception as e:
            print(f"セグメント保存エラー: {e}")

    def upload_file(self, filename):
        try:
            with open(filename, 'rb') as f:
                response = requests.post(self.server_url, files={'file': f})
                
            if response.status_code == 200:
                print(f"アップロード成功: {filename}")
            else:
                print(f"アップロード失敗 ({response.status_code}): {filename}")
                
        except Exception as e:
            print(f"アップロードエラー: {str(e)}")
        finally:
            try:
                os.remove(filename)
            except:
                pass

def main():
    args = parse_arguments()
    recorder = AudioRecorder(args)
    
    try:
        recorder.start()
        while recorder.recording:
            if recorder.should_save_segment:
                recorder.should_save_segment = False  # フラグをリセット
                threading.Thread(target=recorder.save_segment).start()
            time.sleep(0.1)  # より頻繁にチェック
    except KeyboardInterrupt:
        print("\n停止信号を受信しました")
        recorder.stop()
    except Exception as e:
        print(f"エラー発生: {str(e)}")
        recorder.stop()

if __name__ == "__main__":
    main()