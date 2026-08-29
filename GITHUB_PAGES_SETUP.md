# GitHub Pagesで確認サイトを公開する手順

この手順で、MacをシャットダウンしていてもiPhoneから確認サイトを開けるようになります。

## 1. GitHubで新しいリポジトリを作る

1. GitHubにログインします。
2. 右上の `+` から `New repository` を選びます。
3. Repository name を `yahoo-finance-line` にします。
4. 無料でGitHub Pagesを使いやすくするため、`Public` を選びます。
5. `Create repository` を押します。

## 2. このフォルダーのファイルをアップロードする

GitHubの新しいリポジトリ画面で、`uploading an existing file` を選び、このフォルダーのファイルをアップロードします。

最低限必要なもの:

- `.github/workflows/pages-mobile-refresh3.yml`
- `app.py`
- `config.example.json`
- `portfolio_master.py`
- `data/master-xlsx.enc.json`
- `scripts/build_cloud_data.py`
- `scripts/build_cloud_site.py`
- `scripts/decrypt_master.mjs`
- `docs/index.html`
- `docs/.nojekyll`

`outputs/yahoo_finance_portfolio_backup.xlsx`、`config.json`、`.env` は公開リポジトリへアップロードしないでください。銘柄マスターは `data/master-xlsx.enc.json` の暗号化済みファイルだけを置きます。

## 3. 銘柄マスターの復号パスワードをGitHub Secretsに入れる

1. リポジトリの `Settings` を開きます。
2. `Secrets and variables` → `Actions` を開きます。
3. `New repository secret` を押します。
4. Name に `SITE_PASSWORD` と入れます。
5. Secret に、銘柄マスターを暗号化したパスワードを入れます。
6. `Add secret` を押します。

このパスワードはGitHub Actionsが銘柄マスターを読み込むためだけに使います。確認サイトにはパスワード入力画面はありません。

## 4. GitHub PagesをActionsで公開する

1. リポジトリの `Settings` を開きます。
2. `Pages` を開きます。
3. `Build and deployment` の `Source` を `GitHub Actions` にします。

## 5. 最初の公開を実行する

1. リポジトリの `Actions` を開きます。
2. `Update stock dashboard data` を選びます。
3. `Run workflow` を押します。
4. 完了すると `Deploy to GitHub Pages` の中にURLが表示されます。

URLはだいたい次の形になります。

```text
https://あなたのGitHub名.github.io/yahoo-finance-line/
```

## 6. iPhoneで開く

iPhoneでURLを開くと、そのまま確認サイトが表示されます。

## 更新頻度

平日の日本時間9時台から17時台ごろまで、15分に1回の目安で自動更新します。
GitHub Actionsの時刻指定はUTCのため、多少ずれます。

## Yahooの銘柄・ポートフォリオを自動同期する

確認サイトを開いた時と「更新」を押した時に、Google Apps ScriptがYahooファイナンスの
ポートフォリオを確認します。Macを起動しておく必要はありません。

最初に、Google Apps Scriptの「プロジェクトの設定」→「スクリプト プロパティ」で
次のプロパティを1件登録します。

```text
プロパティ: YAHOO_COOKIE
値: Yahooファイナンスへログイン済みのCookieヘッダー
```

Cookieはログイン情報なので、GitHub、メール、チャットには貼り付けないでください。
Yahooのログイン状態が期限切れになった場合は、同じプロパティの値を新しいCookieへ
更新します。それまでは最後に同期できた銘柄・タブ、または公開済みの一覧を表示します。

画面上部の表示は次の意味です。

- `Yahoo同期済み`: 開いた時点のYahooの銘柄・タブを取得しました。
- `Yahoo前回同期リスト`: Yahooへ接続できず、最後に成功した一覧を使っています。
- `Yahoo同期未設定または期限切れ`: Cookieの未設定または期限切れです。

## 注意

- GitHub PagesのURLと表示データは公開されます。URLを知っている人はパスワードなしで閲覧できます。
- LINEのトークンなどの秘密情報はリポジトリへアップロードしないでください。
