import re


def university_acronym(value):
    name = str(value or '').strip()
    if not name:
        return ''
    explicit = re.match(r'^([A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9.\-]{1,14})\s*\(', name)
    if explicit:
        return explicit.group(1).replace('.', '')
    if re.fullmatch(r'[A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9.\-]{1,15}', name):
        return name.replace('.', '')
    words = re.findall(r'[A-Za-zА-Яа-яЁё0-9]+', name)
    if len(words) == 1:
        return words[0][:100]
    ignored = {'имени', 'им', 'имя', 'государственный', 'государственная'}
    meaningful = [word for word in words if word.casefold() not in ignored]
    acronym = ''.join(word[0].upper() for word in meaningful)[:16]
    return acronym if len(acronym) >= 2 else name[:100]
