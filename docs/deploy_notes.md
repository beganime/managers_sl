# Deploy notes ManagerSL

## PDF, DOCX и кириллица

Для генерации PDF с электронной печатью backend использует такую цепочку:

1. DOCX генерируется из шаблона.
2. LibreOffice в headless-режиме конвертирует DOCX в PDF.
3. PyMuPDF накладывает электронную печать и водяной знак на существующую страницу PDF.

На Debian/Ubuntu сервере должны быть установлены:

```bash
apt update
apt install -y libreoffice libreoffice-writer fonts-dejavu-core fonts-liberation
```

Зачем это нужно:

- `libreoffice` и `libreoffice-writer` конвертируют DOCX в PDF без потери структуры документа;
- `fonts-dejavu-core` и `fonts-liberation` дают нормальную поддержку русского, туркменского и английского текста;
- без этих пакетов PDF может не создаться или текст может отображаться некорректно.

В Dockerfile проекта эти зависимости уже указаны. На сервере без Docker их нужно установить вручную.
## LibreOffice exit=137

Если при подтверждении договора появляется `exit=137`, это означает, что Linux убил LibreOffice из-за нехватки оперативной памяти. Это не ошибка DOCX-шаблона.

Для стабильной конвертации на небольшом VPS:

- держите `WEB_CONCURRENCY=1`;
- держите `CELERY_WORKER_CONCURRENCY=1`;
- пересобирайте Docker-образ после изменения Dockerfile;
- добавьте swap 2G на сервере.

Пример swap для Ubuntu/Debian:

```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
free -h
```
