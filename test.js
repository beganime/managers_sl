const leadData = {
    "full_name": "Азат Азатов",
    "phone": "+99365123456",
    "email": "azat@mail.ru",
    "direction": "visa",
    "ФИО студента": "Азат Азатов",
    "Наличие паспорта": "Да",
    "Месяц поездки": "Октябрь",
    "Город вылета": "Ашхабад",
    // Если дата неизвестна, можно передать пустую строку "" или вообще не передавать этот ключ
    "Дата поездки": "" 
};

fetch('https://manager-sl.ru/api/leads/create/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-API-KEY': 'super_secret_key_manager_sl_2026' // Ваш секретный ключ
    },
    body: JSON.stringify(leadData)
})
.then(response => {
    if (response.ok) {
        return response.json();
    }
    throw new Error('Ошибка при отправке');
})
.then(data => {
    console.log('Заявка успешно создана!', data);
})
.catch(error => {
    console.error('Сбой отправки:', error);
});