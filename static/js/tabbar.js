// static/js/tabbar.js
document.addEventListener('DOMContentLoaded', function() {
    // Показываем TabBar только на мобильных устройствах
    if (window.innerWidth > 768) return;

    // Стили для корректного отображения контента над баром (с учетом челки на iOS)
    const style = document.createElement('style');
    style.innerHTML = `
        @media (max-width: 768px) {
            body {
                padding-bottom: calc(80px + env(safe-area-inset-bottom)) !important;
            }
            .unfold-nav-wrapper {
                display: none !important; /* Прячем дефолтное боковое меню Unfold на мобилках */
            }
            /* Плавная анимация нажатия (Telegram-style) */
            .tab-btn {
                -webkit-tap-highlight-color: transparent;
            }
            .tab-btn:active .tab-icon-container {
                transform: scale(0.85);
            }
        }
    `;
    document.head.appendChild(style);

    // Создаем контейнер навигации (премиальный Glassmorphism эффект)
    const nav = document.createElement('nav');
    nav.className = 'fixed bottom-0 left-0 w-full z-[9999] bg-white/85 dark:bg-[#18181b]/85 backdrop-blur-xl border-t border-gray-200/60 dark:border-gray-800/60 pb-[env(safe-area-inset-bottom)] transition-colors duration-300';
    
    const currentPath = window.location.pathname;
    
    // Векторные SVG иконки (солидные и минималистичные)
    const tabs = [
        { 
            id: 'crm', name: 'Сделки', url: '/admin/clients/client/', 
            icon: '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>' 
        },
        { 
            id: 'catalog', name: 'ВУЗы', url: '/admin/catalog/program/', 
            icon: '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 10v6M2 10l10-5 10 5-10 5z"/><path d="M6 12v5c3 3 9 3 12 0v-5"/></svg>' 
        },
        { 
            id: 'home', name: 'Главная', url: '/admin/',
            icon: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>' 
        },
        { 
            id: 'docs', name: 'Документы', url: '/admin/documents/generateddocument/', 
            icon: '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/><line x1="16" x2="8" y1="13" y2="13"/><line x1="16" x2="8" y1="17" y2="17"/><line x1="10" x2="8" y1="9" y2="9"/></svg>' 
        },
        { 
            id: 'profile', name: 'Профиль', url: '/admin/users/user/', 
            icon: '<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 12a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"/><path d="M6 20.2a9 9 0 0 1 12 0"/></svg>' 
        }
    ];

    let html = '<div class="flex justify-between items-center h-[60px] px-1 md:px-4 max-w-lg mx-auto">';
    
    tabs.forEach(tab => {
        // Логика подсветки
        const isActive = tab.id === 'home' 
            ? (currentPath === '/admin/' || currentPath === '/admin')
            : currentPath.startsWith(tab.url);
        
        // Цвета (поддержка Dark Mode)
        const activeColor = 'text-primary-600 dark:text-primary-400';
        const inactiveColor = 'text-gray-400 dark:text-gray-500 hover:text-gray-700 dark:hover:text-gray-300';
        const colorClass = isActive ? activeColor : inactiveColor;
        
        // Фон иконки (появляется только у активного элемента)
        const activeBg = isActive ? 'bg-primary-50 dark:bg-primary-500/10' : '';

        html += `
        <a href="${tab.url}" class="tab-btn flex-1 flex flex-col items-center justify-center h-full gap-1 transition-colors w-[20%] ${colorClass}">
            <div class="tab-icon-container flex items-center justify-center w-10 h-8 rounded-full transition-transform duration-200 ease-out ${activeBg}">
                ${tab.icon}
            </div>
            <span class="text-[10px] tracking-wide ${isActive ? 'font-bold' : 'font-medium'}">${tab.name}</span>
        </a>`;
    });
    
    html += '</div>';
    nav.innerHTML = html;
    
    // Вставляем меню в конец DOM
    document.body.appendChild(nav);
});