# ================================
# 必要なモジュールのインポート
# ================================
from flask import Flask, render_template, request, redirect, url_for, session  # Flask基本機能
from db import insert_user, get_connection  # DB処理用関数
from dotenv import load_dotenv  # .envから環境変数を読み込む
import bcrypt  # パスワードの暗号化・照合に使用
import os  # OS関連操作（環境変数など）
from openai import OpenAI  # OpenAIクライアント
from datetime import datetime  # 登録日時用
from flask import flash, get_flashed_messages
from psycopg2.extras import RealDictCursor
from functools import wraps


# ✅ 管理者専用ページにアクセス制限をかけるデコレーター(※今は管理者がadminのみのため、コレを使わずにlogin()関数内で管理者チェックをしている)
# def admin_required(f):
#     @wraps(f)
#     def decorated_function(*args, **kwargs):
#         if 'username' not in session:
#             flash("⚠️ ログインが必要です。", "error")
#             return redirect(url_for('login'))
#         if not session.get('is_admin'):
#             flash("⚠️ 管理者専用ページです。", "error")
#             return redirect(url_for('assist_select'))  # ← 一般ユーザーのトップページへ戻す
#         return f(*args, **kwargs)
#     return decorated_function

# ================================
# 環境変数の読み込みとOpenAI初期化
# ================================
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ================================
# Flaskアプリの初期化
# ================================
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # セッション管理用（開発用）


# 許可されたユーザーリスト（管理者 or 特定ユーザー）
AUTHORIZED_USERS = ['tanobi_test_login', 'admin']


# ================================
# コードと言語を抽出する関数
# ================================
def extract_code_and_language(raw_code):
    if raw_code.startswith("```"):  # コードが ``` で始まる場合
        lines = raw_code.strip().split('\n')
        language = lines[0].replace("```", "").strip() or "plaintext"  # 言語名取得
        code = '\n'.join(lines[1:-1])  # コード本体
    else:
        language = "plaintext"
        code = raw_code
    return language, code

# ================================
# ルート（ログイン画面）
# ================================
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password'].encode('utf-8')

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE username = %s", (username,))
            user = cur.fetchone()

            if user and bcrypt.checkpw(password, user['password'].encode('utf-8')):
                session['username'] = username
                session['is_admin'] = user['is_admin']  # ← 🔥追加！
                print("userの中身:", user)

                # 👇 adminユーザーなら /admin に飛ばす
                if username == 'admin':
                    return redirect(url_for('admin'))
                else:
                    return redirect(url_for('assist_select'))

            return render_template('login.html', error='ユーザー名またはパスワードが違います。')

        except Exception as e:
            print("ログインエラー:", e)
            return render_template('login.html', error='ログイン中にエラーが発生しました。')

        finally:
            cur.close()
            conn.close()

    return render_template('login.html')

# ================================
# 新規ユーザー登録画面
# ================================
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())

        try:
            insert_user(username, hashed_pw.decode('utf-8'))
            return render_template('signup.html', success='ユーザー登録が完了しました！ログインしてください。')
        except Exception as e:
            print("登録エラー:", e)
            return render_template('signup.html', error='このユーザーIDはすでに使われています。')

    return render_template('signup.html')


# ================================
# 〇〇〇〇〇〇〇〇〇〇〇〇〇〇〇
# ================================
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    username = session.get('username')
    is_admin = session.get('is_admin', False)

    # 管理者でなければ拒否
    if not username or not is_admin:
        return redirect(url_for('assist_select'))

    return render_template('admin.html')


# ================================
# 〇〇〇〇〇〇〇〇〇〇〇〇〇〇〇
# ================================
@app.route('/assist/select', methods=['GET'])
def assist_select():
    username = session.get('username')

    # ログインしてなければログイン画面へ
    if not username:
        return redirect(url_for('login'))

    return render_template('assist_select.html')


# ================================
# ユーザー管理ページ（一覧表示）
# ================================
@app.route('/admin/users', methods=['GET', 'POST'])
def manage_users():

    keyword = ''
    selected_admin = ''
    match_type = 'partial'
    users = []
    error = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        # 🔍 検索条件の処理（POST時）
        if request.method == 'POST':
            keyword = request.form.get('keyword', '').strip()
            selected_admin = request.form.get('is_admin')
            match_type = request.form.get('match_type', 'partial')

            where_clauses = []
            params = []

            # ユーザー名による検索
            if keyword:
                op = '=' if match_type == 'exact' else 'ILIKE'
                pattern = keyword if match_type == 'exact' else f'%{keyword}%'
                where_clauses.append(f"username {op} %s")
                params.append(pattern)

            # 管理者フラグによる絞り込み
            if selected_admin in ('0', '1'):
                where_clauses.append("is_admin = %s")
                is_admin_bool = True if selected_admin == '1' else False
                params.append(is_admin_bool)

            # SQL組み立て
            sql = "SELECT * FROM users"
            if where_clauses:
                sql += " WHERE " + " AND ".join(where_clauses)
            sql += " ORDER BY id"

            cur.execute(sql, tuple(params))

        else:
            # GET時はすべて表示
            cur.execute("SELECT * FROM users ORDER BY id")

        users = cur.fetchall()

    except Exception as e:
        print("ユーザー検索エラー:", e)
        error = "ユーザー一覧の取得中にエラーが発生しました。"

    finally:
        cur.close()
        conn.close()

    return render_template("admin_users.html",
                           users=users,
                           error=error,
                           keyword=keyword,
                           selected_admin=selected_admin,
                           match_type=match_type)


# ================================
# タグ管理ページ
# ================================
# タグ管理ページ（タグ一覧の表示）
@app.route('/admin/tags', methods=['GET', 'POST'])
def manage_tags():
    keyword = ''
    match_type = 'partial'
    tags = []
    error = None

    try:
        conn = get_connection()
        cur = conn.cursor()  # RealDictCursor は使わない！

        # 🔍 検索条件の処理（POST時）
        if request.method == 'POST':
            keyword = request.form.get('keyword', '').strip()
            match_type = request.form.get('match_type', 'partial')

            where_clauses = []
            params = []

            # 〇〇で検索（大文字小文字を区別しない）
            if keyword:
                if match_type == 'exact':
                    where_clauses.append("LOWER(name) = LOWER(%s)")
                    params.append(keyword)
                else:
                    where_clauses.append("name ILIKE %s")
                    params.append(f'%{keyword}%')

            sql = "SELECT * FROM tag"
            
            if where_clauses:
                sql += " WHERE " + " AND ".join(where_clauses)
            sql += " ORDER BY id"

            cur.execute(sql, tuple(params))

        else:
            # GET時はすべて表示
            cur.execute("SELECT * FROM tag ORDER BY id")
        
        tags = cur.fetchall()

    except Exception as e:
        print("タグ検索エラー:", e)
        error = "タグ一覧の取得中にエラーが発生しました。"

    finally:
        cur.close()
        conn.close()

    return render_template("admin_tags.html",
                           tags=tags,
                           error=error,
                           keyword=keyword,
                           match_type=match_type)




# ================================
# アシスト登録ページ
# ================================
@app.route('/assist_register', methods=['GET', 'POST'])
def assist_register():

    try:
        # ✅ tagテーブルからタグ一覧を取得
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM tag ORDER BY id")
        tag_list = cur.fetchall()  # [(1, 'Python'), (2, 'Flask'), ...] のようなリストになる
        tag_dict = {str(row['id']): row['name'] for row in tag_list}  # 🔸IDと名前の辞書を作成

        # セッションに保存されていたタグ名があれば取り出す
        tag_name = session.pop("last_tag_name", None)

    except Exception as e:
        print("タグ取得エラー:", e)
        tag_list = []
        tag_dict = {}


    if request.method == 'POST':
        confirm_clicked = request.form.get('confirm_submit') == '1' #ボタンが押されたかどうか

        word = request.form.get('word')
        details = request.form.get('details')
        tag = request.form.get('tag')
        assist_summary = 'assist_summary' in request.form
        assist_code = 'assist_code' in request.form

        if not word or not details or not tag:
            error = 'すべての項目を入力・選択してください。'
            return render_template('assist_register.html', error=error, tag_list=tag_list)

        if confirm_clicked:
            # ✅ 登録内容を確認ボタンが押されたときのみ ChatGPT 処理へ

            summary_result = ''
            code_result = ''
            code_language = ''

            # ✅ tag_idからtag_nameを取得（ここでしか使わないので辞書から直接取得）
            tag_name = tag_dict.get(tag, "未設定")

            try:
                # ChatGPTで要約を生成
                if assist_summary:
                    summary_prompt = f"""
    以下のワードに対して、学習者が一目で理解できるような超簡潔な説明を作ってください（30文字以内）。
    ワード: {word}
    説明: {details}
    """
                    summary_response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": "あなたは要点を簡潔に伝える教育アシスタントです。"},
                            {"role": "user", "content": summary_prompt}
                        ]
                    )
                    summary_result = summary_response.choices[0].message.content.strip()

                # ChatGPTでコードを生成
                if assist_code:
                    code_prompt = f"""
    以下のワードに関連した実用的なコードを1つだけ提案してください。
    ワード: {word}
    説明: {details}
    タグ: {tag}
    ワード: {word}
    説明: {details}
    上記に関連する{tag}言語のコードを1つ提案してください。Markdown形式でコードのみを表示してください。
    """
                    code_response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": "あなたは優秀なプログラミング教師です。"},
                            {"role": "user", "content": code_prompt}
                        ]
                    )
                    raw_code = code_response.choices[0].message.content.strip()

                    # 言語名とコード本文を分離
                    code_language, code_result = extract_code_and_language(raw_code)

                # 確認画面にデータを渡す
                return render_template('assist_confirm.html',
                                    word=word,
                                    details=details,
                                    tag=tag,  # 🔥 これが必要！
                                    tag_name=tag_name,
                                    summary_result=summary_result,
                                    code_result=code_result,
                                    code_language=code_language)

            except Exception as e:
                print("ChatGPT APIエラー:", e)
                error = f'ChatGPTとの通信に失敗しました。\n{e}'
                return render_template('assist_register.html', error=error, tag_list=tag_list)
        else:
            # ❌ ボタンが違う or フォーム再送信された場合は登録画面に戻す
            return render_template('assist_register.html', tag_list=tag_list)

    # # GET（最初の表示）の場合
    # return render_template('assist_register.html', tag_list=tag_list)

    # ✅ GETアクセス時：flashメッセージがあれば受け取る
    messages = get_flashed_messages(with_categories=True)
    return render_template('assist_register.html', tag_list=tag_list, messages=messages)

# ================================
# 登録確定 → DB保存（重複チェック付き）
# ================================
@app.route('/assist_register/confirm', methods=['POST'])
def assist_register_confirm():

    # フォームから送られたデータを取得
    word = request.form.get('word')  # ワード
    details = request.form.get('details')  # 説明文
    tag_raw = request.form.get('tag')

    # タグIDを整数に変換（失敗時はエラー表示）
    try:
        tag = int(tag_raw)  # 🔥 ここで整数に変換（失敗すると例外）
    except (ValueError, TypeError):
        flash("⚠️ タグが正しく送信されていません。", "error")
        return redirect(url_for('assist_register'))
    
    # オプション項目（空でもOK）
    summary = request.form.get('summary_result') or ''  # 超簡潔な説明
    code = request.form.get('code_result') or ''  # コード
    code_language = request.form.get('code_language') or ''  # コードの言語

    # 登録日時（created_at）と更新日時（updated_at）を現在時刻で設定
    now = datetime.now()

    conn = None  # ← 🔥 追加（初期化）
    cur = None   # ← 🔥 追加（初期化）

    try:
        # PostgreSQLへ接続
        conn = get_connection()
        cur = conn.cursor()

        # ▼▼▼ 既存データとの重複チェックを追加 ▼▼▼
        cur.execute("""
            SELECT * FROM records
            WHERE word = %s AND tag_id = %s
        """, (word, tag))
        existing = cur.fetchone()

        if existing:
            # 同じワード＋タグの組み合わせがすでに存在する場合はエラー
            flash("⚠️ このワードとタグの組み合わせはすでに登録されています。", "error")
            return redirect(url_for('assist_register'))

        # ▼▼▼ 登録処理（INSERT） ▼▼▼
        cur.execute("""
            INSERT INTO records (word, details, tag_id, summary_result, code_result, code_language, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (word, details, tag, summary, code, code_language, now, now))

        conn.commit()  # 変更を確定

        # タグ名を取得（tag ID から name を取得）
        cur.execute("SELECT name FROM tag WHERE id = %s", (tag,))
        tag_name_row = cur.fetchone()
        print("🛠️ tag_name_row の中身:", tag_name_row)  # ← 追加！

        if tag_name_row and 'name' in tag_name_row:
            tag_name = tag_name_row['name']
            session["last_tag_name"] = tag_name # ← タグ名だけ保存しておく
            print("✅ タグ名取得成功:", tag_name)
        else:
            print("❌ タグ名の取得に失敗しました")

        # 成功メッセージを表示
        flash("✅ 登録が完了しました！", "success")
        return redirect(url_for('assist_register'))

    except Exception as e:
        print("例外内容:", e)  # ← ターミナル確認用
        flash(f"⚠️ 登録中にエラーが発生しました: {e}", "error")
        # 予期しないエラーを表示
        error_message = f"⚠️ 登録中にエラーが発生しました: {e}"
        flash(error_message, "error") 
        return redirect(url_for('assist_register'))

    finally:
        # 安全にクローズ（Noneチェック）
        if cur:
            cur.close()
        if conn:
            conn.close()


# ================================
# アシスト検索処理
# ================================
@app.route('/assist_search', methods=['GET', 'POST'])
def assist_search():
    # tag_list = ['Python', 'Flask', 'SQL', 'HTML', 'JavaScript']  # タグの選択肢リスト

    try:
        # ✅ tagテーブルから全タグ取得
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name FROM tag ORDER BY id")
        tag_list = cur.fetchall()  # 例: [(1, 'Python'), (2, 'Flask'), ...]
        tag_dict = {str(row['id']): row['name'] for row in tag_list}  # 🔸id→name辞書を作成

    except Exception as e:
        print("タグ取得エラー:", e)
        tag_list = []
        tag_dict = {}

    results = []  # 検索結果を格納するリスト
    no_result = False  # 結果が見つからなかったときに表示するフラグ

    # 🔍 検索フォームの内容を取得
    if request.method == 'POST':
        keyword = request.form.get('keyword')  # 検索キーワード
        match_type = request.form.get('match_type')  # 完全一致 or 部分一致
        search_word = 'search_word' in request.form  # ワードも検索対象か
        search_details = 'search_details' in request.form  # 説明も検索対象か
        search_assist = 'search_assist' in request.form  # アシストも検索対象か
        search_code = 'search_code' in request.form  # ← アシストコードも検索対象か
        selected_tag = request.form.get('tag')  # タグによる絞り込み

        try:
            conn = get_connection()
            cur = conn.cursor()

            # 検索条件のリストとパラメータを準備
            where_clauses = []
            params = []

            # タグの絞り込み
            if selected_tag:
                where_clauses.append("records.tag_id = %s")
                params.append(int(selected_tag)) # 🔄 数値に変換

            # キーワードの検索対象を構築
            if keyword:
                match_op = "=" if match_type == "exact" else "ILIKE"
                keyword_pattern = keyword if match_type == "exact" else f"%{keyword}%"

                # 検索対象カラムの構築
                keyword_clauses = []
                if search_word:
                    keyword_clauses.append(f"word {match_op} %s")
                    params.append(keyword_pattern)
                if search_details:
                    keyword_clauses.append(f"details {match_op} %s")
                    params.append(keyword_pattern)
                if search_assist:
                    keyword_clauses.append(f"summary_result {match_op} %s")
                    params.append(keyword_pattern)
                if search_code:
                    keyword_clauses.append(f"code_result {match_op} %s")
                    params.append(keyword_pattern)

                 # 🔽 チェックが一つも入っていなかったら、全対象に対して検索するように変更！
                if not keyword_clauses:
                    keyword_clauses.append(f"word {match_op} %s")
                    keyword_clauses.append(f"details {match_op} %s")
                    keyword_clauses.append(f"summary_result {match_op} %s")
                    keyword_clauses.append(f"code_result {match_op} %s")
                    # パラメータは4つ必要になる
                    params.extend([keyword_pattern] * 4)

                 # OR 条件でまとめる
                where_clauses.append(f"({' OR '.join(keyword_clauses)})")

                # # OR 条件でまとめる
                # if keyword_clauses:
                #     where_clauses.append(f"({' OR '.join(keyword_clauses)})")

            # WHERE句を組み立て
            where_sql = " AND ".join(where_clauses)
            sql = """
                SELECT records.*, tag.name AS tag_name
                FROM records
                JOIN tag ON records.tag_id = tag.id
            """
            if where_sql:
                sql += f" WHERE {where_sql}"
            sql += " ORDER BY created_at DESC"  # 新しい順に並べる

            # SQL実行
            cur.execute(sql, tuple(params))
            results = cur.fetchall()

            # 検索結果が0件ならフラグを立てる
            if not results:
                no_result = True

        except Exception as e:
            print("検索処理エラー:", e)
            return render_template("assist_search.html",
                                   error="検索中にエラーが発生しました。",
                                   tag_list=tag_list,
                                   tag_dict=tag_dict)

        finally:
            cur.close()
            conn.close()

    # ページを表示（GET or POST）
    return render_template("assist_search.html",
                           tag_list=tag_list,
                           tag_dict=tag_dict,
                           results=results,
                           no_result=no_result)

# ================================
# # 編集ページ（GET: 表示 / POST: 更新処理）
# ================================
@app.route('/assist_edit/<int:record_id>', methods=['GET', 'POST'])
def assist_edit(record_id):

    try:
        conn = get_connection()
        cur = conn.cursor()  # ✅ RealDictCursorは使わず、登録画面と同じにする

        # ✅ tagテーブルからタグ一覧を取得（登録画面と同じ方法）
        cur.execute("SELECT id, name FROM tag ORDER BY id")
        tag_list = cur.fetchall()

        if request.method == 'POST':
            # フォームから新しいデータを受け取る
            new_word = request.form.get('word')
            new_details = request.form.get('details')
            new_tag_id = request.form.get('tag')  # tagはidとして受け取る（str）

            # 編集時の重複チェック
            cur.execute("""
                SELECT * FROM records 
                WHERE word = %s AND tag_id = %s AND id != %s
            """, (new_word, new_tag_id, record_id))

            existing = cur.fetchone()

            if existing:

                # ✅ flashメッセージとリダイレクト（登録画面と完全一致）
                flash("⚠️ このワードとタグの組み合わせはすでに登録されています。", "error")
                return redirect(url_for('assist_edit', record_id=record_id))
                
                # # 編集対象のデータも再取得
                # cur.execute("SELECT * FROM records WHERE id = %s", (record_id,))
                # record = cur.fetchone()

                # return render_template("assist_edit.html", record=record, tag_list=tag_list, error=error)


            # 更新時刻を記録（更新対象フィールドは word, details, tag, updated_at）
            from datetime import datetime
            updated_at = datetime.now()

            # SQLで更新
            cur.execute("""
                UPDATE records
                SET word = %s, details = %s, tag_id = %s, updated_at = %s
                WHERE id = %s
            """, (new_word, new_details, int(new_tag_id), updated_at, record_id))

            conn.commit()

            # 更新後、検索結果ページへリダイレクト
            # return redirect(url_for('assist_search'))
            flash("✅ 更新登録が完了しました！", "success")
            return redirect(url_for('assist_search'))

        else:
            # 編集対象のレコードを取得してフォームに表示（GET時）
            cur.execute("SELECT * FROM records WHERE id = %s", (record_id,))
            record = cur.fetchone()

            if not record:
                return f"ID {record_id} のデータが見つかりませんでした。", 404

            return render_template("assist_edit.html", record=record, tag_list=tag_list)

    except Exception as e:
        # ✅ 予期しないエラーをflashしてリダイレクト（登録画面と同じ）
        error_message = f"⚠️ 編集中にエラーが発生しました: {e}"
        flash(error_message, "error")
        return redirect(url_for('assist_edit', record_id=record_id))

    finally:
        cur.close()
        conn.close()


# ================================
# データー一覧（削除）
# ================================
@app.route('/assist/delete/<int:record_id>', methods=['POST'])
def assist_delete(record_id):
    try:
        conn = get_connection()
        cur = conn.cursor()

        # 該当レコードを削除
        cur.execute("DELETE FROM records WHERE id = %s", (record_id,))
        conn.commit()

        flash("削除が完了しました。", "success")
    except Exception as e:
        print("削除エラー:", e)
        flash("削除中にエラーが発生しました。", "danger")
    finally:
        cur.close()
        conn.close()

    return redirect(url_for('assist_search'))



# ================================
# 管理者用：ユーザー一覧表示ページ
# ================================
@app.route('/admin/users')
def admin_users():
    try:
        conn = get_connection()
        cur = conn.cursor()

        # ユーザー全件取得
        cur.execute("SELECT id, username, password, is_admin FROM users ORDER BY id")
        users = cur.fetchall()

        return render_template('admin_users.html', users=users)

    except Exception as e:
        print("ユーザー一覧取得エラー:", e)
        return render_template('admin_users.html', error='ユーザー情報の取得中にエラーが発生しました。')

    finally:
        cur.close()
        conn.close()


# ================================
# 🔸 新規ユーザー登録ページを表示するルート
# ================================
@app.route('/admin/users/add', methods=['GET', 'POST'])
def add_user():
    error = None  # エラーメッセージ
    message = None  # 成功メッセージ

    if request.method == 'POST':
        # 🔸 フォームから値を取得
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        is_admin = request.form.get('is_admin')

        # 🔸 バリデーションチェック
        if not username or not password or is_admin not in ('0', '1'):
            error = "すべての項目を正しく入力してください。"
        else:
            try:
                conn = get_connection()
                cur = conn.cursor()

                # 🔸 同じユーザー名が既に存在するかチェック
                cur.execute("SELECT * FROM users WHERE username = %s", (username,))
                existing_user = cur.fetchone()

                if existing_user:
                    error = "このユーザー名はすでに使用されています。"
                else:

                    # ✅ パスワードをハッシュ化（bcrypt）
                    hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
                    hashed_pw_str = hashed_pw.decode('utf-8')  # PostgreSQLに文字列として保存

                    # 🔸 INSERTで登録
                    cur.execute("""
                        INSERT INTO users (username, password, is_admin)
                        VALUES (%s, %s, %s)
                    """, (username, hashed_pw_str, bool(int(is_admin))))

                    conn.commit()

                    # 登録成功後
                    flash("✅ ユーザーの登録が完了しました！")
                    return redirect(url_for('manage_users'))

                    # フォームの入力をクリアしたい場合はここでリダイレクトしてもOK
                    # return redirect(url_for('manage_users'))

            except Exception as e:
                print("ユーザー登録エラー:", e)
                error = "登録中にエラーが発生しました。"

            finally:
                # 安全にクローズ（存在確認）
                if cur:
                    cur.close()
                if conn:
                    conn.close()

    # GET または エラー時はフォーム再表示
    return render_template("admin_users_add.html", error=error, message=message)


# ================================
# 🔸ユーザー編集ページ
# ================================
@app.route('/admin/users/edit/<int:user_id>', methods=['GET', 'POST'])
def edit_user(user_id):
    try:
        conn = get_connection()
        cur = conn.cursor()

        # GET: 編集対象のユーザー情報を取得
        if request.method == 'GET':
            cur.execute("SELECT id, username, is_admin FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()

            if not user:
                return f"ID {user_id} のユーザーが見つかりませんでした。", 404

            return render_template("admin_users_edit.html", user=user)

        # POST: フォームから新しい情報を取得
        new_username = request.form.get('username', '').strip()
        new_is_admin = request.form.get('is_admin', '').strip()

        # バリデーション
        if not new_username or new_is_admin not in ('0', '1'):
            flash("⚠️ ユーザー名と権限を正しく入力してください。", "error")
            return redirect(url_for('edit_user', user_id=user_id))

        # 同じユーザー名が他のIDで使われていないかチェック
        cur.execute("SELECT id FROM users WHERE username = %s AND id != %s", (new_username, user_id))
        existing = cur.fetchone()

        if existing:
            flash("⚠️ このユーザー名は既に使用されています。", "error")
            return redirect(url_for('edit_user', user_id=user_id))

        # パスワード取得（空なら更新しない）
        new_password = request.form.get('password', '').strip()

        # 条件によってSQLを分岐
        if new_password:
            # パスワードをハッシュ化して含めて更新
            hashed_pw = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())

            cur.execute("""
                UPDATE users
                SET username = %s, is_admin = %s, password = %s
                WHERE id = %s
            """, (new_username, new_is_admin == '1', hashed_pw.decode('utf-8'), user_id))

        else:
            # パスワード以外のみ更新
            cur.execute("""
                UPDATE users
                SET username = %s, is_admin = %s
                WHERE id = %s
            """, (new_username, new_is_admin == '1', user_id))


        conn.commit()
        flash("✅ ユーザー情報を更新しました！", "success")
        return redirect(url_for('manage_users'))

    except Exception as e:
        flash(f"⚠️ 編集中にエラーが発生しました: {e}", "error")
        return redirect(url_for('edit_user', user_id=user_id))

    finally:
        cur.close()
        conn.close()

    # return f"ユーザーID {user_id} の編集ページ（仮）"


# ================================
# 削除処理用ルート
# ================================
@app.route('/admin/users/delete/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    try:
        conn = get_connection()
        cur = conn.cursor()

        # 対象ユーザーを削除
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()

        flash("✅ ユーザーを削除しました。", "success")
        return redirect(url_for('manage_users'))

    except Exception as e:
        print("削除エラー:", e)
        flash("⚠️ 削除中にエラーが発生しました。", "error")
        return redirect(url_for('manage_users'))

    finally:
        cur.close()
        conn.close()


# ================================
# 〇〇〇〇〇〇〇〇〇〇〇〇〇〇〇
# ================================
@app.route('/admin/records')
def manage_records():
    return "<h1>登録データ管理ページ（準備中）</h1>"


# ================================
# 新規タグ登録ページを表示するルート
# ================================
@app.route('/admin/tags/add', methods=['GET', 'POST'])
def add_tag():
    error = None
    success = None

    try:
        conn = get_connection()
        cur = conn.cursor()

        if request.method == 'POST':
            tag_name = request.form.get('name', '').strip()

            # 入力チェック
            if not tag_name:
                error = "タグ名を入力してください。"
            else:
                # 重複チェック（同名タグが存在するか）
                cur.execute("SELECT * FROM tag WHERE name = %s", (tag_name,))
                existing = cur.fetchone()

                if existing:
                    error = "⚠️ そのタグ名はすでに存在しています。"
                else:
                    # 新規追加
                    cur.execute("INSERT INTO tag (name) VALUES (%s)", (tag_name,))
                    conn.commit()
                    flash("✅ タグの追加が完了しました！", "success")
                    return redirect(url_for('manage_tags'))

        return render_template('admin_tags_add.html', error=error)

    except Exception as e:
        print("タグ追加エラー:", e)
        error = f"⚠️ タグの追加中にエラーが発生しました：{e}"
        return render_template('admin_tags_add.html', error=error)

    finally:
        cur.close()
        conn.close()


# ================================
# タグ編集画面の表示
# ================================
@app.route('/admin/tags/edit/<int:tag_id>', methods=['GET', 'POST'])
def edit_tag(tag_id):
    try:
        conn = get_connection()
        cur = conn.cursor()

        # GET: 編集対象のタグ情報を取得
        if request.method == 'GET':
            cur.execute("SELECT id, name FROM tag WHERE id = %s", (tag_id,))
            tag = cur.fetchone()

            if not tag:
                return f"ID {tag_id} のタグが見つかりませんでした。", 404

            return render_template("admin_tags_edit.html", tag=tag)

        # POST: 新しいタグ名を取得
        new_name = request.form.get('name', '').strip()

        # バリデーション：空チェック
        if not new_name:
            flash("⚠️ タグ名を入力してください。", "error")
            return redirect(url_for('edit_tag', tag_id=tag_id))

        # 同名チェック（同じID以外に同名があるか）
        cur.execute("SELECT id FROM tag WHERE name = %s AND id != %s", (new_name, tag_id))
        duplicate = cur.fetchone()

        if duplicate:
            flash("⚠️ 同じ名前のタグが既に存在します。", "error")
            return redirect(url_for('edit_tag', tag_id=tag_id))

        # 更新処理
        cur.execute("UPDATE tag SET name = %s WHERE id = %s", (new_name, tag_id))
        conn.commit()

        flash("✅ タグ情報を更新しました！", "success")
        return redirect(url_for('manage_tags'))

    except Exception as e:
        flash(f"⚠️ タグ編集中にエラーが発生しました: {e}", "error")
        return redirect(url_for('edit_tag', tag_id=tag_id))

    finally:
        cur.close()
        conn.close()



# ================================
# タグ削除処理（仮）
# ================================
@app.route('/admin/tags/delete/<int:tag_id>', methods=['POST'])
def delete_tag(tag_id):

    error = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        # 削除クエリの実行
        cur.execute("DELETE FROM tag WHERE id = %s", (tag_id,))
        conn.commit()

        flash("タグを削除しました。", "success")

    except Exception as e:
        print("タグ削除エラー:", e)
        flash("タグの削除中にエラーが発生しました。", "error")

    finally:
        cur.close()
        conn.close()

    return redirect(url_for('manage_tags'))






# ================================
# テスト用：ChatGPTと簡単な通信
# ================================
@app.route('/test_chatgpt')
def test_chatgpt():
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": "こんにちは"}]
        )
        reply = response.choices[0].message.content.strip()
        return f"ChatGPTの返答: {reply}"
    except Exception as e:
        return f"ChatGPT APIとの通信に失敗しました。エラー内容: {e}"

# ================================
# ログイン成功後のダッシュボード
# ================================
@app.route('/dashboard')
def dashboard():
    if 'username' in session:
        return f"ようこそ、{session['username']} さん！ログイン成功です。"
    else:
        return redirect(url_for('login'))
    


# ----------------------------------------
# DB接続テスト用（ブラウザで確認用）
# ----------------------------------------
@app.route("/test_db")
def test_db():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT now();")  # 現在時刻を取得
        result = cur.fetchall()
        cur.close()
        conn.close()
        return f"✅ PostgreSQL接続成功！現在時刻: {result[0]['now']}"
    except Exception as e:
        return f"❌ PostgreSQL接続エラー:<br>{e}"



# # ================================
# # Flaskアプリ起動
# # ================================
# if __name__ == '__main__':
#     app.run(debug=True)
#     cur = conn.cursor()
#     cur.execute("SELECT now();")  # 現在時刻を取得
#     result = cur.fetchall()
#     cur.close()
#     conn.close()
#     return f"✅ PostgreSQL接続成功！現在時刻: {result[0]['now']}"
#     except Exception as e:
#         return f"❌ PostgreSQL接続エラー:<br>{e}"



# ================================
# Flaskアプリ起動
# ================================
if __name__ == '__main__':
    app.run(debug=True)
