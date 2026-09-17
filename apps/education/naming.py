import re


def university_acronym(value):
    name = str(value or '').strip()
    explicit = re.match(r'^([A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9.\-]{1,14})\s*\(', name)
    if explicit:
        return explicit.group(1).replace('.', '')
    words = re.findall(r'[A-Za-zА-Яа-яЁё0-9]+', name)
    ignored = {'имени', 'им', 'имя', 'государственный', 'государственная'}
    meaningful = [word for word in words if word.casefold() not in ignored]
    return ''.join(word[0].upper() for word in meaningful)[:16]
