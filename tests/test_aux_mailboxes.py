import importlib
import os

os.environ.setdefault('SECRET_KEY', 'test-secret-key')
web = importlib.import_module('web_outlook_app')


def client(tmp_path, monkeypatch):
    monkeypatch.setattr(web, 'DATABASE', str(tmp_path / 'accounts.db'))
    monkeypatch.setitem(web.app.config, 'TESTING', True)
    monkeypatch.setitem(web.app.config, 'WTF_CSRF_ENABLED', False)
    with web.app.app_context():
        web.init_db()
        web.set_setting(web.LOGIN_SESSION_VERSION_SETTING_KEY, web.DEFAULT_LOGIN_SESSION_VERSION)
    test_client = web.app.test_client()
    with test_client.session_transaction() as session:
        session['logged_in'] = True
        session['login_session_version'] = web.DEFAULT_LOGIN_SESSION_VERSION
    return test_client


def insert_account(email, account_type='outlook', provider='outlook', imap_host='', imap_port=993):
    with web.app.app_context():
        db = web.get_db()
        cursor = db.execute(
            '''INSERT INTO accounts (email, group_id, account_type, provider, imap_host, imap_port)
               VALUES (?, 1, ?, ?, ?, ?)''',
            (email, account_type, provider, imap_host, imap_port),
        )
        db.commit()
        return cursor.lastrowid


def test_links_existing_custom_imap_and_rejects_invalid_targets(tmp_path, monkeypatch):
    app = client(tmp_path, monkeypatch)
    primary = insert_account('main@outlook.com')
    aux = insert_account(
        'box@wmhotmail.com',
        account_type='imap',
        provider='custom',
        imap_host='mail.wmhotmail.com',
    )
    other = insert_account('other@outlook.com')

    created = app.post(f'/api/accounts/{primary}/aux-mailboxes', json={'aux_account_id': aux})
    assert created.status_code == 200
    body = created.get_json()
    assert body['success'] is True
    assert body['aux_mailbox'] == {
        'id': aux,
        'email': 'box@wmhotmail.com',
        'provider': 'custom',
        'imap_host': 'mail.wmhotmail.com',
        'imap_port': 993,
    }
    assert 'imap_password' not in body['aux_mailbox']

    listed = app.get(f'/api/accounts/{primary}/aux-mailboxes').get_json()
    assert listed['aux_mailboxes'] == [body['aux_mailbox']]
    accounts = app.get('/api/accounts').get_json()['accounts']
    primary_row = next(row for row in accounts if row['id'] == primary)
    assert primary_row['aux_mailboxes'] == [body['aux_mailbox']]

    assert app.post(
        f'/api/accounts/{primary}/aux-mailboxes',
        json={'aux_account_id': primary},
    ).status_code == 400
    assert app.post(
        f'/api/accounts/{primary}/aux-mailboxes',
        json={'aux_account_id': other},
    ).status_code == 400
    assert app.post(
        f'/api/accounts/{primary}/aux-mailboxes',
        json={'aux_account_id': aux},
    ).status_code == 409

    assert app.delete(f'/api/accounts/{primary}/aux-mailboxes/{aux}').status_code == 200
    assert app.get(f'/api/accounts/{primary}/aux-mailboxes').get_json()['aux_mailboxes'] == []
    assert app.delete(f'/api/accounts/{primary}/aux-mailboxes/{aux}').status_code == 404


def test_deleting_aux_account_removes_the_link(tmp_path, monkeypatch):
    app = client(tmp_path, monkeypatch)
    primary = insert_account('main@outlook.com')
    aux = insert_account('box@wmhotmail.com', account_type='imap', provider='custom', imap_host='mail.wmhotmail.com')
    assert app.post(f'/api/accounts/{primary}/aux-mailboxes', json={'aux_account_id': aux}).status_code == 200

    with web.app.app_context():
        assert web.delete_account_by_id(aux) is True

    assert app.get(f'/api/accounts/{primary}/aux-mailboxes').get_json()['aux_mailboxes'] == []
