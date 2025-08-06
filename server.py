from flask import Flask, request, jsonify, send_from_directory
import os
import shutil
from werkzeug.utils import secure_filename

app = Flask(__name__)

# 基本設定
UPLOAD_DIRS = {
    'up1': 'uploads1',
    'up2': 'uploads2',
    'up3': 'uploads3',
    'up4': 'uploads4'
}

# グローバル変数
upload_enabled = True

# ディレクトリ作成
for dir_name in UPLOAD_DIRS.values():
    os.makedirs(dir_name, exist_ok=True)

# アップロード処理
@app.route('/<upload_type>', methods=['POST'])
def upload_file(upload_type):
    global upload_enabled
    
    if not upload_enabled:
        return jsonify({"error": "Upload service is currently stopped"}), 503
    
    if upload_type not in UPLOAD_DIRS:
        return jsonify({"error": "Invalid endpoint"}), 404
    
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file:
        filename = secure_filename(file.filename)
        save_path = os.path.join(UPLOAD_DIRS[upload_type], filename)
        file.save(save_path)
        return jsonify({"message": "File uploaded successfully", "filename": filename}), 200

# ファイル一覧取得
@app.route('/list<list_num>')
def list_files(list_num):
    dir_key = f'up{list_num}'
    if dir_key not in UPLOAD_DIRS:
        return jsonify({"error": "Invalid list number"}), 404
    
    files = os.listdir(UPLOAD_DIRS[dir_key])
    return jsonify({"files": files}), 200

# ファイル取得
@app.route('/get<get_num>/<filename>')
def get_file(get_num, filename):
    dir_key = f'up{get_num}'
    if dir_key not in UPLOAD_DIRS:
        return jsonify({"error": "Invalid endpoint"}), 404
    
    directory = UPLOAD_DIRS[dir_key]
    if not os.path.exists(os.path.join(directory, filename)):
        return jsonify({"error": "File not found"}), 404
    
    return send_from_directory(directory, filename, as_attachment=False)

# すべてのファイル削除
@app.route('/clear', methods=['GET'])
def clear_all_files():
    deleted_files = []
    total_deleted = 0
    
    for dir_name in UPLOAD_DIRS.values():
        if os.path.exists(dir_name):
            files = os.listdir(dir_name)
            for filename in files:
                file_path = os.path.join(dir_name, filename)
                try:
                    os.remove(file_path)
                    deleted_files.append(f"{dir_name}/{filename}")
                    total_deleted += 1
                except Exception as e:
                    return jsonify({"error": f"Failed to delete {file_path}: {str(e)}"}), 500
    
    return jsonify({
        "message": f"Successfully deleted {total_deleted} files",
        "deleted_files": deleted_files,
        "total_deleted": total_deleted
    }), 200

# サービスの状態を取得
@app.route('/status', methods=['GET'])
def get_status():
    global upload_enabled
    
    # ディスク容量を取得
    total, used, free = shutil.disk_usage('.')
    total_gb = total / (1024**3)
    used_gb = used / (1024**3)
    free_gb = free / (1024**3)
    
    # 各ディレクトリの容量を計算
    dir_sizes = {}
    total_files = 0
    
    for dir_name in UPLOAD_DIRS.values():
        if os.path.exists(dir_name):
            dir_size = 0
            file_count = 0
            for filename in os.listdir(dir_name):
                file_path = os.path.join(dir_name, filename)
                if os.path.isfile(file_path):
                    dir_size += os.path.getsize(file_path)
                    file_count += 1
            dir_sizes[dir_name] = {
                "size_bytes": dir_size,
                "size_mb": round(dir_size / (1024**2), 2),
                "file_count": file_count
            }
            total_files += file_count
    
    return jsonify({
        "upload_enabled": upload_enabled,
        "disk_usage": {
            "total_gb": round(total_gb, 2),
            "used_gb": round(used_gb, 2),
            "free_gb": round(free_gb, 2),
            "free_percent": round((free / total) * 100, 2)
        },
        "directories": dir_sizes,
        "total_files": total_files
    }), 200

# サービスを停止
@app.route('/stop', methods=['GET'])
def stop_service():
    global upload_enabled
    upload_enabled = False
    return jsonify({"message": "Service stopped"}), 200

# サービスを開始
@app.route('/start', methods=['GET'])
def start_service():
    global upload_enabled
    upload_enabled = True
    return jsonify({"message": "Service started"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)