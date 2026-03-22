# QR Reader Bridge

iPhoneでQRコードを読み取り、同じLAN上のPCの入力欄へ自動でペーストするツールです。
ブラウザ拡張機能は不要で、**どのアプリの入力欄にも対応**します。

## 仕組み

```
iPhone (Safari) → QR読取 → Flask サーバー → pyautogui → PC側アクティブな入力欄へペースト
```

| コンポーネント | 役割 |
|---|---|
| Python Flask | ローカルサーバー。QRテキストの受信とペーストを担当 |
| iPhone Safari | カメラでQRを読み取り、サーバーへ送信 |
| pyautogui | OS レベルでクリップボード経由のキー入力を実現 |

## 必要環境

- Python 3.9+
- iPhone（Safari）
- PC と iPhone が同じ Wi-Fi に接続されていること

## セットアップ

**1. ライブラリのインストール**

```bash
pip install flask pyautogui pyperclip pyopenssl
```

**2. サーバー起動**

```bash
python app.py
```

**3. PCのローカルIPを確認する**

```bash
# macOS / Linux
ifconfig | grep "inet " | grep -v 127.0.0.1

# Windows
ipconfig
```

**4. iPhoneで以下のURLを開く**

```
https://<PCのIP>:5000/mobile
```

例: `https://192.168.0.50:5000/mobile`

> **Note**
> カメラAPIはHTTPSが必須のため、自己署名証明書を使用しています。
> Safariで「このサイトは安全ではない」と表示されたら「詳細を表示」→「Webサイトを表示」で進んでください。

## 使い方

1. PCで文字を入力したい欄にカーソルを置く
2. iPhoneで「カメラ開始」をタップ
3. QRコードをカメラに向ける
4. 読み取り内容がプレビュー表示される
5. **「PCへ送信」ボタン**をタップ
6. PC側の入力欄に自動ペーストされる

## macOS アクセシビリティ権限

macOS では初回実行時にアクセシビリティ権限が必要です。

「システム設定」→「プライバシーとセキュリティ」→「アクセシビリティ」でターミナル（またはお使いのターミナルアプリ）を許可してください。

## Windows / Linux での利用

`paste_text()` 内のショートカットキーを変更してください。

```python
# Windows
pyautogui.hotkey("ctrl", "v")

# Linux
pyautogui.hotkey("ctrl", "v")
```

## ファイアウォールの設定

LAN内の別端末からアクセスできない場合、5000番ポートの受信を許可してください。

- **Windows**: Windowsファイアウォール → 受信の規則 → ポート5000を許可
- **macOS**: デフォルトで許可されています

## ライセンス

MIT
