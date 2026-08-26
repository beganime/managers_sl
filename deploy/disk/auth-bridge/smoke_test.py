"""Small production smoke test for the private activity store."""

import sqlite3

import app


TEST_USER = 'system-test@local'


def main():
    app.init_activity_db()
    with app.activity_connection() as connection:
        connection.execute('DELETE FROM activity WHERE username = ?', (TEST_USER,))

    app.record_activity({
        'action': 'upload',
        'username': TEST_USER,
        'virtual_path': '/smoke-test.txt',
        'file_size': 1,
    })
    events = app.recent_activity(5)
    assert any(event['username'] == TEST_USER for event in events)

    with app.activity_connection() as connection:
        connection.execute('DELETE FROM activity WHERE username = ?', (TEST_USER,))
    print('activity-store-ok')


if __name__ == '__main__':
    main()
