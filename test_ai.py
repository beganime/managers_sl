def main():
    import g4f

    while True:
        user_input = input("You: ")
        response = g4f.ChatCompletion.create(
            model="gemini-2.5-flash",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": user_input},
            ],
        )
        print("AI:", response)


if __name__ == "__main__":
    main()

