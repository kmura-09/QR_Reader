## できること

* iPhoneでQR読取
* PCのローカルサーバーへ送信
* PCブラウザで**今フォーカス中の input / textarea / contenteditable** に自動入力
* 必要なら Enter も送る

## 構成

* **PC側**: Python Flask
* **iPhone側**: Safariで開く読取ページ
* **PCブラウザ側**: Tampermonkey

---

# 1. PC側 Python サーバー

`app.py`

```python
from flask import Flask, request, jsonify, render_template_string
from threading import Lock
import time

app = Flask(__name__)

store = {
    "text": "",
    "timestamp": 0.0,
}
lock = Lock()

MOBILE_HTML = """
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>QR Reader</title>
  <script src="https://unpkg.com/html5-qrcode"></script>
  <style>
    body {
      font-family: sans-serif;
      padding: 16px;
      line-height: 1.5;
    }
    #reader {
      width: 100%;
      max-width: 360px;
      margin-top: 16px;
    }
    .box {
      margin-top: 12px;
      padding: 12px;
      border: 1px solid #ccc;
      border-radius: 8px;
      word-break: break-all;
    }
    button {
      font-size: 16px;
      padding: 10px 14px;
      margin-right: 8px;
    }
  </style>
</head>
<body>
  <h2>iPhone QR読取</h2>
  <p>PCブラウザで入力欄をクリックしたあと、ここでQRを読んでください。</p>

  <div>
    <button id="startBtn">カメラ開始</button>
    <button id="stopBtn">停止</button>
  </div>

  <div id="reader"></div>
  <div class="box" id="status">待機中</div>

  <script>
    const statusEl = document.getElementById("status");
    let qr = null;
    let started = false;
    let lastText = "";
    let lastTime = 0;

    async function sendText(text) {
      const res = await fetch("/scan", {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ text })
      });

      const data = await res.json();
      statusEl.textContent = "送信: " + text + " / " + JSON.stringify(data);
    }

    async function onScanSuccess(decodedText) {
      const now = Date.now();

      // 同一コードの連投防止
      if (decodedText === lastText && now - lastTime < 1500) {
        return;
      }

      lastText = decodedText;
      lastTime = now;

      try {
        await sendText(decodedText);
      } catch (e) {
        statusEl.textContent = "送信失敗: " + e;
      }
    }

    async function startCamera() {
      if (started) return;

      qr = new Html5Qrcode("reader");
      try {
        await qr.start(
          { facingMode: "environment" },
          {
            fps: 10,
            qrbox: { width: 250, height: 250 }
          },
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
      <li><a href="/latest">/latest</a> : 最新値取得API</li>
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
        return jsonify({"ok": False, "message": "empty text"}), 400

    with lock:
        store["text"] = text
        store["timestamp"] = time.time()

    return jsonify({"ok": True, "text": text})

@app.route("/latest", methods=["GET"])
def latest():
    consume = request.args.get("consume", "1") == "1"

    with lock:
        text = store["text"]
        timestamp = store["timestamp"]
        if consume and text:
            store["text"] = ""
            store["timestamp"] = 0.0

    return jsonify({
        "text": text,
        "timestamp": timestamp
    })

if __name__ == "__main__":
    # 社内LANからアクセスできるように 0.0.0.0
    app.run(host="0.0.0.0", port=5000, debug=True)
```

---

# 2. インストールと起動

```bash
pip install flask
python app.py
```

PCのIPがたとえば `192.168.0.50` なら、iPhoneで開くURLはこれです。

```text
http://192.168.0.50:5000/mobile
```

---

# 3. Tampermonkey スクリプト

PCのChromeに Tampermonkey を入れて、新規スクリプトへ貼ってください。
`192.168.0.50` は自分のPCのIPに変えてください。

```javascript
// ==UserScript==
// @name         QR to Active Element
// @namespace    local.qr.bridge
// @version      1.0
// @description  iPhoneで読んだQR文字列を、現在フォーカス中の入力欄へ流し込む
// @match        http://*/*
// @match        https://*/*
// @grant        GM_xmlhttpRequest
// @connect      192.168.0.50
// ==/UserScript==

(function () {
  'use strict';

  const SERVER_URL = 'http://192.168.0.50:5000/latest?consume=1';
  const POLL_MS = 800;
  const MODE = 'replace'; // 'replace' or 'append'
  const SEND_ENTER = false;
  const SEND_TAB = false;

  let isPolling = false;

  function log(...args) {
    console.log('[QR-BRIDGE]', ...args);
  }

  function getDeepActiveElement(doc = document) {
    let active = doc.activeElement;
    while (active && active.shadowRoot && active.shadowRoot.activeElement) {
      active = active.shadowRoot.activeElement;
    }
    return active;
  }

  function isEditable(el) {
    if (!el) return false;

    if (el.isContentEditable) return true;

    const tag = (el.tagName || '').toUpperCase();
    if (tag === 'TEXTAREA') return true;

    if (tag === 'INPUT') {
      const type = (el.type || 'text').toLowerCase();
      const allowed = [
        'text', 'search', 'url', 'tel', 'password', 'email', 'number'
      ];
      return allowed.includes(type);
    }

    return false;
  }

  function setNativeValue(element, value) {
    const proto = Object.getPrototypeOf(element);
    const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');

    if (descriptor && descriptor.set) {
      descriptor.set.call(element, value);
    } else {
      element.value = value;
    }

    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function insertTextAtCaretInput(el, text, mode = 'replace') {
    el.focus();

    if (mode === 'replace') {
      setNativeValue(el, text);
      return;
    }

    const start = el.selectionStart ?? el.value.length;
    const end = el.selectionEnd ?? el.value.length;
    const current = el.value || '';
    const newValue = current.slice(0, start) + text + current.slice(end);

    setNativeValue(el, newValue);

    const newPos = start + text.length;
    try {
      el.setSelectionRange(newPos, newPos);
    } catch (e) {}
  }

  function insertTextAtCaretContentEditable(el, text, mode = 'replace') {
    el.focus();

    if (mode === 'replace') {
      el.textContent = text;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
      return;
    }

    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) {
      el.textContent += text;
    } else {
      const range = selection.getRangeAt(0);
      range.deleteContents();
      range.insertNode(document.createTextNode(text));
      range.collapse(false);
      selection.removeAllRanges();
      selection.addRange(range);
    }

    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function sendKey(el, keyName) {
    const eventInit = {
      key: keyName,
      code: keyName,
      bubbles: true,
      cancelable: true
    };

    el.dispatchEvent(new KeyboardEvent('keydown', eventInit));
    el.dispatchEvent(new KeyboardEvent('keypress', eventInit));
    el.dispatchEvent(new KeyboardEvent('keyup', eventInit));
  }

  function insertToActiveElement(text) {
    const el = getDeepActiveElement();

    if (!isEditable(el)) {
      log('フォーカス中の要素が入力対象ではありません', el);
      return false;
    }

    if (el.isContentEditable) {
      insertTextAtCaretContentEditable(el, text, MODE);
    } else {
      insertTextAtCaretInput(el, text, MODE);
    }

    if (SEND_ENTER) sendKey(el, 'Enter');
    if (SEND_TAB) sendKey(el, 'Tab');

    log('入力完了:', text, el);
    return true;
  }

  function fetchLatest() {
    if (isPolling) return;
    isPolling = true;

    GM_xmlhttpRequest({
      method: 'GET',
      url: SERVER_URL,
      onload: function (res) {
        isPolling = false;

        try {
          const data = JSON.parse(res.responseText);
          if (data.text) {
            insertToActiveElement(data.text);
          }
        } catch (e) {
          log('JSON parse error', e, res.responseText);
        }
      },
      onerror: function (err) {
        isPolling = false;
        log('poll error', err);
      },
      ontimeout: function () {
        isPolling = false;
        log('poll timeout');
      }
    });
  }

  setInterval(fetchLatest, POLL_MS);
  log('started');
})();
```

---

# 4. 使い方

1. PCで Tampermonkey を有効化
2. など、入力したいWebアプリを開く
3. **入れたい欄を先にクリックしてカーソルを置く**
4. iPhoneで `http://PCのIP:5000/mobile` を開く
5. カメラ開始
6. QRを読む
7. PC側の今フォーカス中の欄に値が入る

---

# 5. この方式の強み

専用にDOMを追わなくていいので、かなり楽です。

使える対象はだいたいこんな感じです。

*  Lightning
* Googleフォーム
* 社内Webシステム
* 検索欄
* テキストエリア
* 一部のリッチテキスト欄

---

# 6. ハマりどころ

## React系 / 系

単純な `el.value = ...` だと内部状態に反映されないことがあります。
そのため上のスクリプトでは **native setter + input/change発火** を入れています。

## フォーカスがずれる

iPhoneで読取中にPC側のフォーカスは変わらないですが、PCで別操作をすると別要素に入るので、**入力前に対象欄をクリック**が基本です。

## 一部の独自コンポーネント

 Lightningの一部入力は、見た目は欄でも内部構造が特殊なことがあります。
その場合でも多くは通りますが、画面によって微調整が必要です。

---

# 7. まず最初に試すべき場所

なら、最初は以下で試すのがよいです。

* グローバル検索欄
* レコード詳細の単純なテキスト項目
* フィルタ条件の検索欄

いきなり複雑な lookup 項目や独自LWC項目だと少しクセがあります。

---

# 8. 実運用向けの改良案

次に足すならこの順です。

* **音を鳴らす**
  受信成功時にPCかiPhoneでピッ音
* **重複送信防止強化**
  同じQRを数秒無視
* **Enter送信モード**
  検索欄なら読み取り後に自動検索
* **ホワイトリスト制御**
  ドメインだけで動かす
* **ポップアップ表示**
  何を受信したかPC画面右下に出す

---

# 9. かなり大事な補足

社内LANで使うなら、PCのWindowsファイアウォールで **5000番ポート** の受信許可が必要になることがあります。
iPhoneから `/mobile` が開けなければ、まずそこを確認です。

---

# 10. 次の一手

このままでも動きますが、実務ではたぶん

* 読み取ったら **現在欄へ入力 + Enter**
* あるいは **現在欄へ入力 + Tab**
* QR値の先頭/末尾を整形してから投入

まで欲しくなるはずです。

その場合は、あなたの使いたい画面に合わせて
**向けに Enter 自動実行つき版** まで詰められます。
