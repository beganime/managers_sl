"""Upload and remove one tiny object to verify production S3 connectivity."""

import io

import app


def main():
    folder = '_system-tests'
    key = app.upload_client_file(folder, 'healthcheck.pdf', io.BytesIO(b'%PDF-1.4\n%%EOF'), 'application/pdf')
    try:
        metadata = app.S3_CLIENT.head_object(Bucket=app.S3_BUCKET, Key=key)
        assert metadata['ContentLength'] > 0
        print('s3-upload-ok')
    finally:
        app.S3_CLIENT.delete_object(Bucket=app.S3_BUCKET, Key=key)


if __name__ == '__main__':
    main()
