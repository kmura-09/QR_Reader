from flask import Flask, request, jsonify, render_template_string
import pyperclip
import pyautogui
import time
import threading
import platform

app = Flask(__name__)

# QR受信後、ペーストするまでの待機時間（秒）
# iPhoneで読んだ後にPCの欄へフォーカスを戻す時間
PASTE_DELAY = 0.5

MOBILE_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QR Reader</title>
  <script src="https://unpkg.com/html5-qrcode"></script>
  <style>
    * { box-sizing: border-box; }
    body { font-family: sans-serif; padding: 12px; padding-bottom: 140px; line-height: 1.4; }
    #reader { width: 100%; max-width: 360px; margin-top: 8px; }
    .box {
      margin-top: 8px; padding: 10px;
      border: 1px solid #ccc; border-radius: 8px;
      word-break: break-all; font-size: 15px;
    }
    button { font-size: 16px; padding: 10px 14px; margin-right: 8px; }
    #bottomBar {
      position: fixed; bottom: 0; left: 0; right: 0;
      background: #fff; border-top: 1px solid #ddd;
      padding: 10px 12px;
    }
  </style>
</head>
<body>
  <h2>iPhone QR読取</h2>
  <p>PC側の入力欄にカーソルを置いてから、QRを読んでください。</p>

  <div>
    <button id="startBtn">カメラ開始</button>
    <button id="stopBtn">停止</button>
  </div>

  <div id="reader"></div>
  <div class="box" id="status">待機中</div>

  <div id="bottomBar">
    <label style="font-size:15px; display:block; margin-bottom:8px;">
      <input type="checkbox" id="addTime" style="width:18px; height:18px; vertical-align:middle; margin-right:6px;">
      日付・時刻を付加
    </label>
    <div id="preview" style="display:none; font-size:14px; color:#333; margin-bottom:8px; word-break:break-all;"></div>
    <button id="sendBtn" style="display:none; width:100%; font-size:18px; padding:14px; background:#007aff; color:white; border:none; border-radius:10px;">PCへ送信</button>
  </div>

  <script>
    const statusEl = document.getElementById("status");
    const previewEl = document.getElementById("preview");
    const sendBtn = document.getElementById("sendBtn");
    const addTimeEl = document.getElementById("addTime");
    let qr = null;
    let started = false;
    let pendingText = "";

    function currentTime() {
      const now = new Date();
      const y = now.getFullYear();
      const mo = String(now.getMonth() + 1).padStart(2, "0");
      const d = String(now.getDate()).padStart(2, "0");
      const h = String(now.getHours()).padStart(2, "0");
      const m = String(now.getMinutes()).padStart(2, "0");
      return y + "/" + mo + "/" + d + " " + h + ":" + m;
    }

    function buildText(raw) {
      return addTimeEl.checked ? currentTime() + " " + raw : raw;
    }

    async function sendText(text) {
      const res = await fetch("/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text })
      });
      return await res.json();
    }

    async function onScanSuccess(decodedText) {
      if (decodedText === pendingText) return;
      pendingText = decodedText;
      previewEl.textContent = buildText(decodedText);
      previewEl.style.display = "block";
      sendBtn.style.display = "block";
      statusEl.textContent = "読取済み";
    }

    sendBtn.addEventListener("click", async () => {
      if (!pendingText) return;
      const textToSend = buildText(pendingText);
      try {
        await sendText(textToSend);
        statusEl.textContent = "送信完了: " + textToSend;
        previewEl.style.display = "none";
        sendBtn.style.display = "none";
        pendingText = "";
      } catch (e) {
        statusEl.textContent = "送信失敗: " + e;
      }
    });

    async function startCamera() {
      if (started) return;
      qr = new Html5Qrcode("reader");
      try {
        await qr.start(
          { facingMode: "environment" },
          { fps: 10, qrbox: { width: 250, height: 250 } },
          onScanSuccess
        );
        started = true;
        statusEl.textContent = "カメラ起動中";
      } catch (e) {
        statusEl.textContent = "カメラ起動失敗: " + e;
      }
    }

    async function stopCamera() {
      if (!started || !qr) return;
      try {
        await qr.stop();
        await qr.clear();
        started = false;
        statusEl.textContent = "停止しました";
      } catch (e) {
        statusEl.textContent = "停止失敗: " + e;
      }
    }

    document.getElementById("startBtn").addEventListener("click", startCamera);
    document.getElementById("stopBtn").addEventListener("click", stopCamera);
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    return """
    <h2>QR Bridge Server</h2>
    <ul>
      <li><a href="/mobile">/mobile</a> : iPhone読取画面</li>
    </ul>
    """

@app.route("/mobile")
def mobile():
    return render_template_string(MOBILE_HTML)

@app.route("/scan", methods=["POST"])
def scan():
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()

    if not text:
        return jsonify({"ok": False, "message": "empty"}), 400

    # 別スレッドでペースト（レスポンスを先に返すため）
    threading.Thread(target=paste_text, args=(text,), daemon=True).start()

    return jsonify({"ok": True, "text": text})

def paste_text(text):
    time.sleep(PASTE_DELAY)
    pyperclip.copy(text)
    if platform.system() == "Darwin":
        pyautogui.hotkey("command", "v")
    else:
        pyautogui.hotkey("ctrl", "v")
    print(f"[QR] ペースト: {text}")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3001, debug=False, ssl_context="adhoc")
