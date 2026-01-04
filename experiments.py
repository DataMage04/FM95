items = list(range(1, 56))  # Example list with 55 items
PAGE_SIZE = 25

page = 0
max_page = (len(items) - 1) // PAGE_SIZE

while True:
    start = page * PAGE_SIZE
    end = start + PAGE_SIZE

    print(f"\nPage {page + 1} of {max_page + 1}")
    print(items[start:end])

    command = input("Enter 'n' for next, 'p' for previous, 'q' to quit: ").lower()

    if command == "n" and page < max_page:
        page += 1
    elif command == "p" and page > 0:
        page -= 1
    elif command == "q":
        break
    else:
        print("Invalid command.")
