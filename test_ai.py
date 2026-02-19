import g4f

while True:
    user_input = input("You: ")
    response = g4f.ChatCompletion.create(
        model="gpt-4",
        # model="gemini-2.5-flash",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": user_input},
        ],
    )
    print("AI:", response)

