import psycopg2  # PostgreSQLに接続するためのライブラリ
from psycopg2.extras import RealDictCursor  # クエリ結果を辞書形式で取得できるようにする
from dotenv import load_dotenv  # .envファイルから環境変数を読み込むライブラリ
import os  # OSから環境変数を取得するための標準ライブラリ

# .envファイルを読み込む（プロジェクト起動時に一度実行）
load_dotenv()

# .envファイルから接続用URL（DATABASE_URL）を取得
DATABASE_URL = os.getenv("DATABASE_URL")

# PostgreSQLへの接続を返す関数（共通して使えるようにする）
def get_connection():
    # 接続処理（失敗時はエラーが発生）
    return psycopg2.connect(
        DATABASE_URL,                # .envに設定された接続URLを使用
        sslmode="require",           # SSL接続を要求（RenderのDBなどで必要）
        cursor_factory=RealDictCursor  # 結果を辞書形式で受け取る（カラム名付き）
    )

# ユーザー登録を行う関数（Flaskのsignup処理などから呼び出す用）
def insert_user(username, hashed_password):
    try:
        # データベースへ接続
        conn = get_connection()
        cur = conn.cursor()

        # usersテーブルにデータを挿入（nicknameは省略）
        cur.execute(
            "INSERT INTO users (username, password) VALUES (%s, %s)",
            (username, hashed_password)
        )

        # 変更内容を保存（INSERTなどの操作では必要）
        conn.commit()

    except Exception as e:
        # エラー発生時に内容を表示し、上位にエラーを送る
        print("ユーザー登録エラー:", e)
        raise

    finally:
        # カーソルと接続をクローズしてリソースを開放
        cur.close()
        conn.close()


# recordsテーブルに新しいデータを挿入する関数
def insert_record(word, details, tag, summary_result, code_result, code_language, created_at, updated_at):
    try:
        # PostgreSQLに接続
        conn = get_connection()
        cur = conn.cursor()

        # INSERT文を実行してデータを追加
        cur.execute("""
            INSERT INTO records
            (word, details, tag, summary_result, code_result, code_language, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            word,             # ワード
            details,          # 説明
            tag,              # タグ（言語）
            summary_result,   # デキスギの要約
            code_result,      # コード例
            code_language,    # コードの言語（例：python, javascript）
            created_at,       # 作成日時
            updated_at        # 更新日時
        ))

        # 変更を保存（コミット）
        conn.commit()

    except Exception as e:
        # エラーが発生した場合は内容を表示して再送出
        print("登録エラー:", e)
        raise

    finally:
        # 使用後はカーソルと接続を閉じる
        cur.close()
        conn.close()

