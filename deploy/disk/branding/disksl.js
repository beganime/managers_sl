(function () {
    'use strict';

    const ownerUsername = 'begenchyagmurow2008@gmail.com';

    function getCurrentUsername() {
        const element = document.querySelector('.menu-content .wrap-word');
        return String(element?.textContent || '').trim().toLowerCase();
    }

    function applyAccessUI() {
        const username = getCurrentUsername();
        if (username && username !== ownerUsername) {
            document.querySelectorAll(
                'a[href$="/web/client/shares"], a[href$="/web/client/mfa"]'
            ).forEach((link) => link.closest('.menu-item')?.remove());

            if (/\/web\/client\/(shares|mfa)\/?$/.test(window.location.pathname)) {
                window.location.replace('/web/client/files');
            }
        }

        document.querySelectorAll('body *').forEach((element) => {
            if (element.children.length) return;
            const value = String(element.textContent || '').trim();
            if (/^SFTPGo\s+2\.7\.1\b/i.test(value)) {
                element.style.display = 'none';
            }
        });
    }

    applyAccessUI();

    if (!window.location.pathname.startsWith('/web/client/files')) {
        return;
    }

    const categories = ['Бюджет', 'Контракт', 'Гослиния', 'Магистры'];
    const params = new URLSearchParams(window.location.search);
    const currentPath = decodeURIComponent(params.get('path') || '/');
    const parts = currentPath.split('/').filter(Boolean);
    const currentYear = /^20\d{2}$/.test(parts[0] || '') ? parts[0] : '';
    const currentCategory = categories.includes(parts[1]) ? parts[1] : '';
    const defaultYear = String(new Date().getFullYear() + 1);

    const cardTitle = document.querySelector('.card-title');
    if (!cardTitle || document.getElementById('disksl-tools')) {
        return;
    }

    const cardHeader = cardTitle.closest('.card-header');
    const cardToolbar = cardHeader?.querySelector('.card-toolbar');
    if (!cardHeader || !cardToolbar) {
        return;
    }

    const localSearch = cardTitle.querySelector('input[data-kt-filemanager-table-filter="search"]');
    const localSearchContainer = localSearch?.parentElement;
    if (localSearch) {
        localSearch.placeholder = 'Поиск в текущей папке';
        localSearch.setAttribute('aria-label', 'Поиск в текущей папке');
    }

    const toggleButton = document.createElement('button');
    toggleButton.type = 'button';
    toggleButton.id = 'disksl-tools-toggle';
    toggleButton.className = 'btn btn-flex btn-light-primary me-3';
    toggleButton.setAttribute('aria-expanded', 'false');
    toggleButton.setAttribute('aria-controls', 'disksl-tools-panel');
    toggleButton.textContent = 'Поиск и фильтры';
    cardToolbar.prepend(toggleButton);

    const activityButton = document.createElement('button');
    activityButton.type = 'button';
    activityButton.id = 'disksl-activity-toggle';
    activityButton.className = 'btn btn-flex btn-light-primary me-3';
    activityButton.setAttribute('aria-expanded', 'false');
    activityButton.setAttribute('aria-controls', 'disksl-activity-panel');
    activityButton.textContent = 'Активность';
    cardToolbar.prepend(activityButton);

    const panel = document.createElement('div');
    panel.id = 'disksl-tools-panel';
    panel.className = 'disksl-tools-panel';
    panel.hidden = true;

    const tools = document.createElement('div');
    tools.id = 'disksl-tools';
    tools.className = 'disksl-tools';
    tools.innerHTML = `
        <div class="disksl-field">
            <label class="disksl-label" for="disksl-year">Учебный год</label>
            <select id="disksl-year" class="disksl-control"></select>
        </div>
        <div class="disksl-field">
            <label class="disksl-label" for="disksl-category">Категория</label>
            <select id="disksl-category" class="disksl-control">
                <option value="">Все категории</option>
                ${categories.map((category) => `<option value="${category}">${category}</option>`).join('')}
            </select>
        </div>
        <div class="disksl-field disksl-field--search">
            <label class="disksl-label" for="disksl-global-search">Поиск студента</label>
            <input id="disksl-global-search" class="disksl-control" type="search"
                placeholder="ФИО или SL-ID" autocomplete="off">
            <div id="disksl-results" class="disksl-results"></div>
        </div>`;
    if (localSearchContainer) {
        const localField = document.createElement('div');
        const localLabel = document.createElement('label');
        localField.className = 'disksl-field disksl-field--local';
        localLabel.className = 'disksl-label';
        localLabel.textContent = 'Текущая папка';
        localLabel.htmlFor = 'disksl-local-search';
        localSearch.id = 'disksl-local-search';
        localField.append(localLabel, localSearchContainer);
        tools.prepend(localField);
    }
    panel.appendChild(tools);
    cardHeader.insertAdjacentElement('afterend', panel);

    const activityPanel = document.createElement('section');
    activityPanel.id = 'disksl-activity-panel';
    activityPanel.className = 'disksl-activity-panel';
    activityPanel.hidden = true;
    activityPanel.innerHTML = `
        <div class="disksl-activity-header">
            <div>
                <div class="disksl-activity-title">Последние действия</div>
                <div class="disksl-activity-subtitle">Кто и что изменял в DiskSL</div>
            </div>
            <button type="button" id="disksl-activity-refresh" class="btn btn-sm btn-light-primary">Обновить</button>
        </div>
        <div id="disksl-activity-list" class="disksl-activity-list"></div>`;
    panel.insertAdjacentElement('afterend', activityPanel);

    const usagePanel = document.createElement('section');
    usagePanel.id = 'disksl-usage';
    usagePanel.className = 'disksl-usage';
    usagePanel.innerHTML = `
        <div class="disksl-usage-chart" role="img" aria-label="Заполнение хранилища">
            <div id="disksl-usage-percent" class="disksl-usage-percent">—</div>
        </div>
        <div class="disksl-usage-copy">
            <div class="disksl-usage-title">Хранилище DiskSL</div>
            <div id="disksl-usage-values" class="disksl-usage-values">Загрузка данных…</div>
        </div>`;
    activityPanel.insertAdjacentElement('afterend', usagePanel);

    function formatBytes(value) {
        const bytes = Math.max(Number(value) || 0, 0);
        if (bytes < 1024) return `${bytes} Б`;
        const units = ['КБ', 'МБ', 'ГБ', 'ТБ'];
        let amount = bytes;
        let unit = -1;
        do { amount /= 1024; unit += 1; } while (amount >= 1024 && unit < units.length - 1);
        return `${amount >= 10 ? amount.toFixed(1) : amount.toFixed(2)} ${units[unit]}`;
    }

    async function loadUsage() {
        try {
            const response = await fetch('/web/client/disksl/usage', {credentials: 'same-origin'});
            if (!response.ok) throw new Error('usage unavailable');
            const payload = await response.json();
            const percent = Math.max(0, Math.min(Number(payload.usage_percent) || 0, 100));
            usagePanel.style.setProperty('--disksl-usage', `${percent * 3.6}deg`);
            document.getElementById('disksl-usage-percent').textContent = `${percent.toFixed(1)}%`;
            document.getElementById('disksl-usage-values').textContent =
                `Занято ${formatBytes(payload.used_bytes)} · Свободно ${formatBytes(payload.free_bytes)} · Всего ${formatBytes(payload.total_bytes)}`;
        } catch (_error) {
            document.getElementById('disksl-usage-values').textContent = 'Данные о хранилище временно недоступны';
        }
    }
    loadUsage();

    toggleButton.addEventListener('click', () => {
        const shouldOpen = panel.hidden;
        panel.hidden = !shouldOpen;
        toggleButton.setAttribute('aria-expanded', String(shouldOpen));
        toggleButton.classList.toggle('active', shouldOpen);
        if (shouldOpen) {
            window.setTimeout(() => document.getElementById('disksl-global-search')?.focus(), 0);
        }
    });

    const activityList = document.getElementById('disksl-activity-list');
    const activityActions = {
        upload: 'Загрузил(а)',
        download: 'Скачал(а)',
        delete: 'Удалил(а)',
        rename: 'Переименовал(а)',
        mkdir: 'Создал(а) папку',
        rmdir: 'Удалил(а) папку',
        copy: 'Скопировал(а)'
    };

    function formatActivityTime(value) {
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return '';
        return new Intl.DateTimeFormat('ru-RU', {
            day: '2-digit', month: '2-digit', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        }).format(date);
    }

    function activityPath(event) {
        const path = String(event.virtual_path || '').replace(/^\/+/, '');
        const target = String(event.virtual_target_path || '').replace(/^\/+/, '');
        if (event.action === 'rename' && target) return `${path} → ${target}`;
        return path || target || '/';
    }

    async function loadActivity() {
        activityList.innerHTML = '<div class="disksl-activity-empty">Загрузка…</div>';
        try {
            const response = await fetch('/web/client/disksl/activity', {
                credentials: 'same-origin',
                headers: {'X-Requested-With': 'DiskSL'}
            });
            if (!response.ok) throw new Error('Activity unavailable');
            const payload = await response.json();
            const events = Array.isArray(payload.events) ? payload.events : [];
            activityList.replaceChildren();
            if (!events.length) {
                activityList.innerHTML = '<div class="disksl-activity-empty">Действий пока нет</div>';
                return;
            }
            for (const event of events) {
                const row = document.createElement('div');
                const main = document.createElement('div');
                const meta = document.createElement('div');
                const user = document.createElement('strong');
                const action = document.createElement('span');
                const path = document.createElement('span');
                row.className = 'disksl-activity-row';
                main.className = 'disksl-activity-main';
                meta.className = 'disksl-activity-meta';
                user.textContent = String(event.username || '—');
                action.textContent = activityActions[event.action] || String(event.action || 'Действие');
                path.textContent = activityPath(event);
                main.append(user, document.createTextNode(' · '), action);
                meta.append(path, document.createTextNode(' · ' + formatActivityTime(event.event_at)));
                row.append(main, meta);
                activityList.appendChild(row);
            }
        } catch (_error) {
            activityList.innerHTML = '<div class="disksl-activity-empty">Журнал временно недоступен</div>';
        }
    }

    activityButton.addEventListener('click', () => {
        const shouldOpen = activityPanel.hidden;
        activityPanel.hidden = !shouldOpen;
        activityButton.setAttribute('aria-expanded', String(shouldOpen));
        activityButton.classList.toggle('active', shouldOpen);
        if (shouldOpen) loadActivity();
    });
    document.getElementById('disksl-activity-refresh').addEventListener('click', loadActivity);

    const yearSelect = document.getElementById('disksl-year');
    const categorySelect = document.getElementById('disksl-category');
    const globalSearch = document.getElementById('disksl-global-search');
    const results = document.getElementById('disksl-results');
    const thisYear = new Date().getFullYear();
    const years = new Set();
    for (let year = thisYear - 1; year <= thisYear + 5; year += 1) {
        years.add(String(year));
    }
    if (currentYear) years.add(currentYear);
    yearSelect.innerHTML = [...years]
        .sort()
        .map((year) => `<option value="${year}">${year}</option>`)
        .join('');
    yearSelect.value = currentYear || defaultYear;
    categorySelect.value = currentCategory;

    function filesUrl(path) {
        const query = new URLSearchParams({path});
        return `/web/client/files?${query.toString()}`;
    }

    function directoryUrl(path) {
        const query = new URLSearchParams({path});
        return `/web/client/dirs?${query.toString()}`;
    }

    yearSelect.addEventListener('change', () => {
        const path = categorySelect.value
            ? `/${yearSelect.value}/${categorySelect.value}`
            : `/${yearSelect.value}`;
        window.location.assign(filesUrl(path));
    });

    categorySelect.addEventListener('change', () => {
        const path = categorySelect.value
            ? `/${yearSelect.value}/${categorySelect.value}`
            : `/${yearSelect.value}`;
        window.location.assign(filesUrl(path));
    });

    const cache = new Map();

    async function loadStudents(year, category) {
        const cacheKey = `${year}/${category || '*'}`;
        if (cache.has(cacheKey)) return cache.get(cacheKey);
        const selectedCategories = category ? [category] : categories;
        const groups = await Promise.all(selectedCategories.map(async (item) => {
            const response = await fetch(directoryUrl(`/${year}/${item}`), {
                credentials: 'same-origin',
                headers: {'X-Requested-With': 'DiskSL'}
            });
            if (!response.ok) return [];
            const entries = await response.json();
            return entries
                .filter((entry) => String(entry.type) === '1')
                .map((entry) => ({
                    name: String(entry.name || '').trim(),
                    href: String(entry.url || ''),
                    category: item
                }))
                .filter((entry) => entry.name && entry.href.startsWith('/web/client/files?'));
        }));
        const students = groups.flat();
        cache.set(cacheKey, students);
        return students;
    }

    function closeResults() {
        results.classList.remove('is-open');
        results.innerHTML = '';
    }

    let searchTimer;
    globalSearch.addEventListener('input', () => {
        window.clearTimeout(searchTimer);
        const term = globalSearch.value.trim().toLocaleLowerCase('ru');
        if (term.length < 2) {
            closeResults();
            return;
        }
        searchTimer = window.setTimeout(async () => {
            results.innerHTML = '<div class="disksl-result-empty">Поиск…</div>';
            results.classList.add('is-open');
            try {
                const students = await loadStudents(yearSelect.value, categorySelect.value);
                const matches = students
                    .filter((student) => student.name.toLocaleLowerCase('ru').includes(term))
                    .slice(0, 30);
                results.replaceChildren();
                if (!matches.length) {
                    const empty = document.createElement('div');
                    empty.className = 'disksl-result-empty';
                    empty.textContent = 'Студент не найден';
                    results.appendChild(empty);
                    return;
                }
                for (const student of matches) {
                    const link = document.createElement('a');
                    const categoryLabel = document.createElement('small');
                    link.className = 'disksl-result';
                    link.href = student.href;
                    link.append(document.createTextNode(student.name), document.createElement('br'));
                    categoryLabel.textContent = student.category;
                    link.appendChild(categoryLabel);
                    results.appendChild(link);
                }
            } catch (_error) {
                results.innerHTML = '<div class="disksl-result-empty">Поиск временно недоступен</div>';
            }
        }, 300);
    });

    document.addEventListener('click', (event) => {
        if (!tools.contains(event.target)) closeResults();
    });
})();
