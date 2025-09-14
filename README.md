# HR FAQ & Leave Application Chatbot

This project is an **HR FAQ & Leave Application Chatbot** built with [RASA](https://rasa.com/).  
It can answer HR-related queries (leave policy, salary dates, attendance rules, company details, job openings) and also allow employees to apply for leave.

---

##  Features
- HR FAQs (leave policy, salary date, attendance rules, company details, job openings).
- Leave application form (leave type, start date, end date, reason, leave days).
- Multi-language support (English + Bengali).
- Saves leave applications to a **SQLite database**.
- Validation for leave type, dates, and number of leave days.
- Small talk (greetings, thanks, goodbye).
- Fallback handling for unknown queries.

---

### Installation

> This project works with **Python 3.10 only**.  
> Please make sure you have Python 3.10 installed before proceeding.

1. Clone the repository:
   ```bash
   git clone <https://github.com/Naima-345/Github-Repo>
   cd hr-chatbot
Create a virtual environment (recommended):

bash
Copy
Edit
python3.10 -m venv venv
source enve_test/bin/activate   # Linux/Mac
enve_test\Scripts\activate      # Windows
Install dependencies from requirements.txt:

bash
Copy
Edit
pip install -r requirements.txt
    ```



## ▶️ Running the Bot

1.  Train the model:

    ``` bash
    rasa train
    ```

2.  Start the action server (for DB integration):

    ``` bash
    rasa run actions
    ```

3.  Run the chatbot in shell mode:

    ``` bash
    rasa shell
    ```



##  Testing the Bot

Try these sample queries:

-   FAQs
    -   "What is the leave policy?"
    -   "When is salary credited?"
    -   "What are the attendance rules?"
    -   "Tell me about the company."
    -   "Are there any job openings?"
-   Leave Application
    -   "I want to apply for sick leave."
    -   "Apply for annual leave from 20/08/2025 to 25/08/2025."
    -   "I need 3 days casual leave."
-   Small Talk
    -   "Hello"
    -   "Thanks"
    -   "Goodbye"

##  Database

The chatbot stores leave requests in a SQLite database:
`leave_applications.db`

**Table structure:**

``` sql
CREATE TABLE leave_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    leave_type TEXT,
    start_date TEXT,
    end_date TEXT,
    reason TEXT,
    leave_days INTEGER
);
```


##  Future Improvements

-   Email notification to HR after leave submission.
-   Web UI for employees.
-   Integration with full HR system.
-   More advanced NLP for Bengali queries.
-   Bangla and English separated 
