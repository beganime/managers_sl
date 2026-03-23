set -e
echo "🔄 Получаем последний код..."
git pull origin main
echo "🐳 Собираем и перезапускаем контейнеры..."
docker compose build --no-cache
docker compose up -d
echo "✅ Готово!"
echo ""
echo "Полезные команды:"
echo "  docker compose logs -f web   — логи Django"
echo "  docker compose logs -f nginx — логи Nginx"
echo "  docker compose exec web python manage.py createsuperuser"
echo "  docker compose down          — остановить"