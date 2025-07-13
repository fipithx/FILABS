from datetime import datetime
from bson import ObjectId
from utils import get_mongo_db, trans, format_currency, clean_currency
from flask import current_app, session
from flask_login import current_user
import logging

# Unified logger for the application
logger = logging.getLogger('ficore_app')
logger.setLevel(logging.INFO)

# Course and quiz data
courses_data = {
    "budgeting_101": {
        "id": "budgeting_101",
        "title_en": "Budgeting 101",
        "title_ha": "Tsarin Kudi 101",
        "description_en": "Learn the basics of budgeting and financial planning to manage your household expenses in Northern Nigeria, using Naira.",
        "description_ha": "Koyon asalin tsarin kudi da shirye-shiryen kudi don sarrafa kudin gida a Arewacin Najeriya, ta amfani da Naira.",
        "title_key": "learning_hub_course_budgeting101_title",
        "desc_key": "learning_hub_course_budgeting101_desc",
        "is_premium": False,
        "roles": ["trader", "personal", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_income_title",
                "title_en": "Understanding Income",
                "title_ha": "Fahimtar Kuɗin Shiga",
                "lessons": [
                    {
                        "id": "budgeting_101-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_income_sources_title",
                        "title_en": "Income Sources",
                        "title_ha": "Tushen Kuɗin Shiga",
                        "content_type": "video",
                        "content_path": "Uploads/budgeting_101_lesson1.mp4",
                        "content_en": "Understanding different sources of income is crucial for effective budgeting. Learn about salary, business income from local markets like Sabon Gari, and Halal investments.",
                        "content_ha": "Fahimtar tushen kuɗin shiga yana da mahimmanci don tsarin kudi mai inganci. Koyi game da albashi, kuɗin shiga na kasuwanci daga kasuwanni kamar Sabon Gari, da jarin Halal.",
                        "quiz_id": "quiz-1-1"
                    },
                    {
                        "id": "budgeting_101-module-1-lesson-2",
                        "title_key": "learning_hub_lesson_net_income_title",
                        "title_en": "Calculating Net Income",
                        "title_ha": "Ƙididdigar Kuɗin Shiga Bayan Haraji",
                        "content_type": "text",
                        "content_key": "learning_hub_lesson_net_income_content",
                        "content_en": "Learn how to calculate your net income after taxes and deductions, such as Zakat or PAYE, to create a realistic budget for your family in Kano or Kaduna.",
                        "content_ha": "Koyi yadda ake ƙididdigar kuɗin shiga bayan haraji da ragi, kamar Zakat ko PAYE, don ƙirƙirar kasafin kudi na gaske ga iyalinku a Kano ko Kaduna.",
                        "quiz_id": None
                    }
                ]
            },
            {
                "id": "module-2",
                "title_key": "learning_hub_module_expenses_title",
                "title_en": "Managing Expenses",
                "title_ha": "Sarrafa Kuɗaɗen Ciwon",
                "lessons": [
                    {
                        "id": "budgeting_101-module-2-lesson-1",
                        "title_key": "learning_hub_lesson_expense_categories_title",
                        "title_en": "Expense Categories",
                        "title_ha": "Rukunin Kuɗaɗen Ciwon",
                        "content_type": "text",
                        "content_en": "Learn to categorize your expenses into fixed (e.g., rent), variable (e.g., food in local markets), and discretionary spending (e.g., Sallah celebrations) to better manage your budget.",
                        "content_ha": "Koyi yadda ake rarraba kuɗaɗen kuɗin ku zuwa tsayayye (misali, haya), mai canzawa (misali, abinci a kasuwannin gida), da kashewa na zaɓi (misali, bukukuwan Sallah) don sarrafa kasafin kuɗin ku mafi kyau.",
                        "quiz_id": None
                    }
                ]
            }
        ]
    },
    "islamic_finance_101": {
        "id": "islamic_finance_101",
        "title_en": "Islamic Finance Principles",
        "title_ha": "Ƙa'idodin Kuɗi na Musulunci",
        "description_en": "Understand Halal investments, Zakat calculations, and ethical saving practices aligned with Sharia principles for Northern Nigerian communities.",
        "description_ha": "Fahimci jarin Halal, ƙididdigar Zakat, da al'adun ajiya masu ɗa'a da suka dace da ƙa'idodin Shari'a ga al'ummomin Arewacin Najeriya.",
        "title_key": "learning_hub_course_islamic_finance_title",
        "desc_key": "learning_hub_course_islamic_finance_desc",
        "is_premium": False,
        "roles": ["trader", "personal", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_islamic_finance_title",
                "title_en": "Introduction to Islamic Finance",
                "title_ha": "Gabatarwa ga Kuɗi na Musulunci",
                "lessons": [
                    {
                        "id": "islamic_finance_101-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_halal_investments_title",
                        "title_en": "Halal Investments",
                        "title_ha": "Jarin Halal",
                        "content_type": "text",
                        "content_en": "Learn about Sharia-compliant investment options, such as Sukuk and equity funds, suitable for Northern Nigerian investors.",
                        "content_ha": "Koyi game da zaɓuɓɓukan jari da suka dace da Shari'a, kamar Sukuk da kuɗin hannun jari, waɗanda suka dace da masu saka hannun jari a Arewacin Najeriya.",
                        "quiz_id": "quiz-islamic-finance-1"
                    }
                ]
            }
        ]
    },
    "savings_basics": {
        "id": "savings_basics",
        "title_en": "Saving for the Future",
        "title_ha": "Ajiya don Gaba",
        "description_en": "Discover strategies to save for Hajj, marriage, or children’s education in a Northern Nigerian context.",
        "description_ha": "Gano dabarun ajiya don Hajji, aure, ko ilimin yara a yanayin Arewacin Najeriya.",
        "title_key": "learning_hub_course_savings_basics_title",
        "desc_key": "learning_hub_course_savings_basics_desc",
        "is_premium": False,
        "roles": ["trader", "personal", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_savings_title",
                "title_en": "Savings Strategies",
                "title_ha": "Dabarun Ajiya",
                "lessons": [
                    {
                        "id": "savings_basics-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_savings_strategies_title",
                        "title_en": "Effective Savings Strategies",
                        "title_ha": "Dabarun Ajiya Mai Inganci",
                        "content_type": "text",
                        "content_key": "learning_hub_lesson_savings_strategies_content",
                        "content_en": "Learn proven strategies for building savings, including the 50/30/20 rule, automatic savings through Nigerian banks, and planning for an emergency fund.",
                        "content_ha": "Koyi dabarun da aka tabbatar don gina ajiya, ciki har da ƙa'idar 50/30/20, ajiyar atomatik ta bankunan Najeriya, da shirya asusun gaggawa.",
                        "quiz_id": None
                    },
                    {
                        "id": "savings_basics-module-1-lesson-2",
                        "title_key": "learning_hub_lesson_savings_goals_title",
                        "title_en": "Setting Savings Goals",
                        "title_ha": "Saita Maƙasudin Ajiya",
                        "content_type": "text",
                        "content_en": "Discover how to set realistic savings goals for events like Hajj or children’s education in Northern Nigeria.",
                        "content_ha": "Gano yadda ake saita maƙasudin ajiya na gaske don abubuwan kamar Hajji ko ilimin yara a Arewacin Najeriya.",
                        "quiz_id": "quiz-savings-1"
                    }
                ]
            }
        ]
    },
    "business_budgeting_101": {
        "id": "business_budgeting_101",
        "title_en": "Budgeting for Small Businesses",
        "title_ha": "Tsarin Kudi don Ƙananan Kasuwanci",
        "description_en": "Learn to manage finances for your shop in Kano’s Sabon Gari market or Kaduna’s Central Market.",
        "description_ha": "Koyi yadda ake sarrafa kudi don shagon ku a kasuwar Sabon Gari ta Kano ko kasuwar Central ta Kaduna.",
        "title_key": "learning_hub_course_business_budgeting_title",
        "desc_key": "learning_hub_course_business_budgeting_desc",
        "is_premium": False,
        "roles": ["trader", "personal", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_business_budgeting_title",
                "title_en": "Business Budgeting Basics",
                "title_ha": "Asalin Tsarin Kudi na Kasuwanci",
                "lessons": [
                    {
                        "id": "business_budgeting_101-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_business_expenses_title",
                        "title_en": "Tracking Business Expenses",
                        "title_ha": "Bin Didigin Kuɗaɗen Kasuwanci",
                        "content_type": "text",
                        "content_en": "Learn to track expenses for your small business, such as inventory costs in local markets or transport fees.",
                        "content_ha": "Koyi yadda ake bin didigin kuɗaɗen kasuwancin ku, kamar farashin kaya a kasuwannin gida ko kuɗin sufuri.",
                        "quiz_id": None
                    }
                ]
            }
        ]
    },
    "marketing_101": {
        "id": "marketing_101",
        "title_en": "Marketing in Local Markets",
        "title_ha": "Tallace-tallace a Kasuwannin Gida",
        "description_en": "Discover how to promote your products using WhatsApp and local radio in Northern Nigeria.",
        "description_ha": "Gano yadda ake tallata kayan ku ta amfani da WhatsApp da rediyon gida a Arewacin Najeriya.",
        "title_key": "learning_hub_course_marketing_title",
        "desc_key": "learning_hub_course_marketing_desc",
        "is_premium": False,
        "roles": ["trader", "personal", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_marketing_title",
                "title_en": "Local Marketing Strategies",
                "title_ha": "Dabarun Tallace-tallace na Gida",
                "lessons": [
                    {
                        "id": "marketing_101-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_whatsapp_marketing_title",
                        "title_en": "WhatsApp Marketing",
                        "title_ha": "Tallace-tallace ta WhatsApp",
                        "content_type": "text",
                        "content_en": "Learn to use WhatsApp to promote your products to customers in Kano and Kaduna, including creating business groups and sharing updates.",
                        "content_ha": "Koyi yadda ake amfani da WhatsApp don tallata kayan ku ga abokan ciniki a Kano da Kaduna, ciki har da ƙirƙirar ƙungiyoyin kasuwanci da raba sabuntawa.",
                        "quiz_id": "quiz-marketing-1"
                    }
                ]
            }
        ]
    },
    "business_compliance_101": {
        "id": "business_compliance_101",
        "title_en": "Business Compliance Basics",
        "title_ha": "Asalin Bin Dokokin Kasuwanci",
        "description_en": "Understand CAC registration and tax obligations for small businesses in Nigeria.",
        "description_ha": "Fahimci rajistar CAC da wajibcin haraji ga ƙananan kasuwanci a Najeriya.",
        "title_key": "learning_hub_course_compliance_title",
        "desc_key": "learning_hub_course_compliance_desc",
        "is_premium": False,
        "roles": ["trader", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_compliance_title",
                "title_en": "Compliance Requirements",
                "title_ha": "Bukatar Bin Dokoki",
                "lessons": [
                    {
                        "id": "business_compliance_101-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_cac_registration_title",
                        "title_en": "CAC Registration",
                        "title_ha": "Rajistar CAC",
                        "content_type": "text",
                        "content_en": "Learn the steps to register your business with the Corporate Affairs Commission (CAC) in Nigeria.",
                        "content_ha": "Koyi matakan rajistar kasuwancin ku tare da Hukumar Kula da Harkokin Kamfanoni (CAC) a Najeriya.",
                        "quiz_id": None
                    }
                ]
            }
        ]
    },
    "mobile_banking_101": {
        "id": "mobile_banking_101",
        "title_en": "Mobile Banking Basics",
        "title_ha": "Asalin Bankin Wayar Hannu",
        "description_en": "Learn to facilitate mobile transactions for customers in rural Northern Nigeria using platforms like M-Pesa or Nigerian banking apps.",
        "description_ha": "Koyi yadda ake sauƙaƙe cinikin wayar hannu ga abokan ciniki a ƙauyukan Arewacin Najeriya ta amfani da dandamali kamar M-Pesa ko manhajojin banki na Najeriya.",
        "title_key": "learning_hub_course_mobile_banking_title",
        "desc_key": "learning_hub_course_mobile_banking_desc",
        "is_premium": False,
        "roles": ["agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_mobile_banking_title",
                "title_en": "Mobile Banking Operations",
                "title_ha": "Ayyukan Bankin Wayar Hannu",
                "lessons": [
                    {
                        "id": "mobile_banking_101-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_mobile_transactions_title",
                        "title_en": "Handling Mobile Transactions",
                        "title_ha": "Rikodin Cinikin Wayar Hannu",
                        "content_type": "text",
                        "content_en": "Learn to process mobile transactions securely for customers in rural areas, ensuring trust and efficiency.",
                        "content_ha": "Koyi yadda ake sarrafa cinikin wayar hannu cikin aminci ga abokan ciniki a yankunan karkara, tabbatar da amana da inganci.",
                        "quiz_id": None
                    }
                ]
            }
        ]
    },
    "customer_service_101": {
        "id": "customer_service_101",
        "title_en": "Customer Service for Agents",
        "title_ha": "Sabis na Abokin Ciniki ga Wakilai",
        "description_en": "Develop skills to assist customers in Hausa and English with trust and professionalism.",
        "description_ha": "Ƙware a ƙwarewar taimakon abokan ciniki a cikin Hausa da Turanci tare da amana da ƙwarewa.",
        "title_key": "learning_hub_course_customer_service_title",
        "desc_key": "learning_hub_course_customer_service_desc",
        "is_premium": False,
        "roles": ["agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_customer_service_title",
                "title_en": "Customer Service Basics",
                "title_ha": "Asalin Sabis na Abokin Ciniki",
                "lessons": [
                    {
                        "id": "customer_service_101-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_communication_skills_title",
                        "title_en": "Communication Skills",
                        "title_ha": "Ƙwarewar Sadarwa",
                        "content_type": "text",
                        "content_en": "Learn effective communication techniques to build trust with customers in Northern Nigerian communities.",
                        "content_ha": "Koyi dabarun sadarwa masu inganci don gina amana tare da abokan ciniki a cikin al'ummomin Arewacin Najeriya.",
                        "quiz_id": None
                    }
                ]
            }
        ]
    },
    "fraud_prevention_101": {
        "id": "fraud_prevention_101",
        "title_en": "Fraud Prevention",
        "title_ha": "Rigakafin Zamba",
        "description_en": "Identify and prevent financial scams targeting communities in Northern Nigeria.",
        "description_ha": "Gano da hana zamba na kuɗi da ke niyya ga al'ummomin Arewacin Najeriya.",
        "title_key": "learning_hub_course_fraud_prevention_title",
        "desc_key": "learning_hub_course_fraud_prevention_desc",
        "is_premium": False,
        "roles": ["agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_fraud_prevention_title",
                "title_en": "Fraud Detection",
                "title_ha": "Gano Zamba",
                "lessons": [
                    {
                        "id": "fraud_prevention_101-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_fraud_identification_title",
                        "title_en": "Identifying Scams",
                        "title_ha": "Gano Zamba",
                        "content_type": "text",
                        "content_en": "Learn to recognize common financial scams, such as phishing or fake mobile banking apps, targeting Northern Nigerian customers.",
                        "content_ha": "Koyi yadda ake gane zamba na kuɗi na kowa, kamar phishing ko manhajojin banki na karya, waɗanda ke niyya ga abokan ciniki na Arewacin Najeriya.",
                        "quiz_id": None
                    }
                ]
            }
        ]
    },
    "tax_reforms_2025": {
        "id": "tax_reforms_2025",
        "title_en": "Tax Reforms 2025",
        "title_ha": "Gyaran Haraji na 2025",
        "description_en": "Understand the key changes in Nigeria's 2025 tax reforms, including updates to PIT, CIT, and VAT, for businesses and individuals in Northern Nigeria.",
        "description_ha": "Fahimci mahimman canje-canje a cikin gyaran haraji na Najeriya na 2025, ciki har da sabuntawa ga PIT, CIT, da VAT, ga kasuwanci da daidaikun mutane a Arewacin Najeriya.",
        "title_key": "learning_hub_course_tax_reforms_2025_title",
        "desc_key": "learning_hub_course_tax_reforms_2025_desc",
        "is_premium": False,
        "roles": ["trader", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_tax_reforms_title",
                "title_en": "Understanding Nigeria's 2025 Tax Reforms",
                "title_ha": "Fahimtar Gyaran Haraji na Najeriya 2025",
                "lessons": [
                    {
                        "id": "tax_reforms_2025-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_tax_reforms_title",
                        "title_en": "Key Tax Reform Changes",
                        "title_ha": "Mahimman Canje-canjen Gyaran Haraji",
                        "content_type": "text",
                        "content_key": "learning_hub_lesson_tax_reforms_content",
                        "content_en": """
### Personal Income Tax (PIT) Changes
- Individuals earning ₦1,000,000 or less annually now enjoy ₦200,000 rent relief, reducing their taxable income to ₦800,000.
- Result: No PIT for most low-income earners in Northern Nigeria.

### Value Added Tax (VAT) Relief
- No VAT on essential goods/services: food (e.g., yam, rice), education, rent, healthcare, baby products, electricity.
- Helps families in Kano and Kaduna reduce cost of living.

### Corporate Income Tax (CIT) Reforms
- **Small businesses (≤₦50,000,000 turnover):**
  - Now pay 0% CIT.
  - Can file simpler tax returns, no audited accounts required.
- **Large companies:**
  - CIT reduced from 30% to 27.5% (2025).
  - Further reduction to 25% in later years.
  - Can now claim VAT credits on eligible expenses.
                        """,
                        "content_ha": """
### Canje-canjen Harajin Kuɗin Shiga na Mutum (PIT)
- Mutanen da ke samun ₦1,000,000 ko ƙasa da haka a shekara yanzu suna jin daɗin tallafin haya na ₦200,000, wanda ke rage kuɗin shiga masu haraji zuwa ₦800,000.
- Sakamako: Babu PIT ga yawancin masu karɓar kuɗi kaɗan a Arewacin Najeriya.

### Tallafin Harajin Ƙarin Daraja (VAT)
- Babu VAT akan kayayyaki/sabis masu mahimmanci: abinci (misali, dawa, shinkafa), ilimi, haya, kiwon lafiya, kayan jarirai, wutar lantarki.
- Yana taimaka wa iyalai a Kano da Kaduna rage farashin rayuwa.

### Gyaran Harajin Kuɗin Kamfanoni (CIT)
- **Ƙananan kasuwanci (≤₦50,000,000 na kuɗin shiga):**
  - Yanzu suna biyan 0% CIT.
  - Za su iya shigar da bayanan haraji mafi sauƙi, ba a buƙatar asusun da aka duba.
- **Manyan kamfanoni:**
  - CIT ya rage daga 30% zuwa 27.5% (2025).
  - Ƙarin ragi zuwa 25% a shekaru masu zuwa.
  - Yanzu suna iya neman tallafin VAT akan kuɗaɗen da suka cancanta.
                        """,
                        "quiz_id": "quiz-tax-reforms-2025"
                    }
                ]
            }
        ]
    },
    "regulatory_compliance_101": {
        "id": "regulatory_compliance_101",
        "title_en": "Regulatory Compliance",
        "title_ha": "Bin Dokokin Gwamnati",
        "description_en": "Learn about CAC registration and other regulatory requirements for Northern Nigerian businesses.",
        "description_ha": "Koyi game da rajistar CAC da sauran buƙatun doka ga kasuwancin Arewacin Najeriya.",
        "title_key": "learning_hub_course_regulatory_compliance_title",
        "desc_key": "learning_hub_course_regulatory_compliance_desc",
        "is_premium": False,
        "roles": ["trader", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_regulatory_compliance_title",
                "title_en": "Regulatory Basics",
                "title_ha": "Asalin Dokoki",
                "lessons": [
                    {
                        "id": "regulatory_compliance_101-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_regulatory_requirements_title",
                        "title_en": "Understanding Regulations",
                        "title_ha": "Fahimtar Dokoki",
                        "content_type": "text",
                        "content_en": "Understand the key regulatory requirements for operating a business in Nigeria, including CAC registration and local permits.",
                        "content_ha": "Fahimci mahimman buƙatun doka don gudanar da kasuwanci a Najeriya, ciki har da rajistar CAC da izinin gida.",
                        "quiz_id": None
                    }
                ]
            }
        ]
    },
    "aml_101": {
        "id": "aml_101",
        "title_en": "Anti-Money Laundering Basics",
        "title_ha": "Asalin Hana Haramtacciyar Kuɗi",
        "description_en": "Understand AML regulations to protect your business and community from financial crimes in Northern Nigeria.",
        "description_ha": "Fahimci dokokin AML don kare kasuwancin ku da al'ummar ku daga laifukan kuɗi a Arewacin Najeriya.",
        "title_key": "learning_hub_course_aml_title",
        "desc_key": "learning_hub_course_aml_desc",
        "is_premium": False,
        "roles": ["trader", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_aml_title",
                "title_en": "AML Fundamentals",
                "title_ha": "Asalin AML",
                "lessons": [
                    {
                        "id": "aml_101-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_aml_basics_title",
                        "title_en": "AML Principles",
                        "title_ha": "Ƙa'idodin AML",
                        "content_type": "text",
                        "content_en": "Learn the basics of Anti-Money Laundering (AML) regulations and how to apply them in Northern Nigerian financial transactions.",
                        "content_ha": "Koyi asalin dokokin Hana Haramtacciyar Kuɗi (AML) da yadda ake amfani da su a cikin cinikin kuɗi na Arewacin Najeriya.",
                        "quiz_id": None
                    }
                ]
            }
        ]
    },
    "digital_foundations": {
        "id": "digital_foundations",
        "title_en": "Digital Foundations",
        "title_ha": "Tushen Dijital",
        "description_en": "Learn the basics of computers, internet tools, and how to use AI tools like ChatGPT for everyday tasks in Northern Nigeria. No prior knowledge needed!",
        "description_ha": "Koyon asalin kwamfutoci, kayan aikin intanet, da yadda ake amfani da kayan aikin AI kamar ChatGPT don ayyukan yau da kullum a Arewacin Najeriya. Ba a buƙatar ilimi na farko!",
        "title_key": "learning_hub_digital_foundations_title",
        "desc_key": "learning_hub_digital_foundations_desc",
        "is_premium": False,
        "roles": ["trader", "personal", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_computer_basics_title",
                "title_en": "Computer Basics",
                "title_ha": "Asalin Kwamfuta",
                "lessons": [
                    {
                        "id": "digital_foundations-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_computer_basics_title",
                        "title_en": "What is a Computer?",
                        "title_ha": "Menene Kwamfuta?",
                        "content_type": "text",
                        "content_en": "Understand the basic components of a computer and how to use it for everyday tasks in Northern Nigeria, such as budgeting or communication.",
                        "content_ha": "Fahimci abubuwan asali na kwamfuta da yadda ake amfani da ita don ayyukan yau da kullum a Arewacin Najeriya, kamar tsarin kudi ko sadarwa.",
                        "quiz_id": None
                    },
                    {
                        "id": "digital_foundations-module-1-lesson-2",
                        "title_key": "learning_hub_lesson_files_title",
                        "title_en": "Saving vs. Uploading Files",
                        "title_ha": "Ajiya vs. Loda Fayiloli",
                        "content_type": "text",
                        "content_en": "Learn the difference between saving a file locally and uploading it to the cloud or a website, optimized for low-bandwidth environments.",
                        "content_ha": "Koyi bambanci tsakanin ajiye fayil a cikin gida da loda shi zuwa gajimare ko gidan yanar gizo, wanda aka inganta don yanayin ƙarancin bandwidth.",
                        "quiz_id": None
                    }
                ]
            },
            {
                "id": "module-2",
                "title_key": "learning_hub_module_internet_tools_title",
                "title_en": "Internet Tools",
                "title_ha": "Kayan Aikin Intanet",
                "lessons": [
                    {
                        "id": "digital_foundations-module-2-lesson-1",
                        "title_key": "learning_hub_lesson_browser_title",
                        "title_en": "What is a Browser?",
                        "title_ha": "Menene Mai Bincike?",
                        "content_type": "video",
                        "content_path": "Uploads/browser_intro.mp4",
                        "content_en": "Explore how to use web browsers like Chrome to access the internet effectively, even with limited connectivity in Northern Nigeria.",
                        "content_ha": "Bincika yadda ake amfani da masu bincike na yanar gizo kamar Chrome don samun damar intanet yadda ya kamata, ko da tare da ƙarancin haɗin kai a Arewacin Najeriya.",
                        "quiz_id": None
                    }
                ]
            },
            {
                "id": "module-3",
                "title_key": "learning_hub_module_ai_basics_title",
                "title_en": "AI for Beginners",
                "title_ha": "AI ga Masu Fara",
                "lessons": [
                    {
                        "id": "digital_foundations-module-3-lesson-1",
                        "title_key": "learning_hub_lesson_ai_budgeting_title",
                        "title_en": "Using ChatGPT for Budgeting",
                        "title_ha": "Amfani da ChatGPT don Tsarin Kudi",
                        "content_type": "text",
                        "content_en": "Learn how to use AI tools like ChatGPT to assist with budgeting and financial planning for your household or small business in Northern Nigeria.",
                        "content_ha": "Koyi yadda ake amfani da kayan aikin AI kamar ChatGPT don taimakawa da tsarin kudi da shirye-shiryen kudi ga gidan ku ko ƙananan kasuwanci a Arewacin Najeriya.",
                        "quiz_id": "quiz-digital-foundations-3-1"
                    }
                ]
            }
        ]
    },
    "spreadsheets_101": {
        "id": "spreadsheets_101",
        "title_en": "Using Spreadsheets for Finance",
        "title_ha": "Amfani da Spreadsheet don Kuɗi",
        "description_en": "Master Google Sheets to track expenses for your household or business in Northern Nigeria.",
        "description_ha": "Ƙware a Google Sheets don bin didigin kuɗaɗen gida ko kasuwancin ku a Arewacin Najeriya.",
        "title_key": "learning_hub_course_spreadsheets_title",
        "desc_key": "learning_hub_course_spreadsheets_desc",
        "is_premium": False,
        "roles": ["trader", "personal", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_spreadsheets_title",
                "title_en": "Spreadsheet Basics",
                "title_ha": "Asalin Spreadsheet",
                "lessons": [
                    {
                        "id": "spreadsheets_101-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_spreadsheet_basics_title",
                        "title_en": "Introduction to Google Sheets",
                        "title_ha": "Gabatarwa ga Google Sheets",
                        "content_type": "text",
                        "content_en": "Learn the basics of Google Sheets to track expenses, such as market purchases or school fees, in Northern Nigeria.",
                        "content_ha": "Koyi asalin Google Sheets don bin didigin kuɗaɗen, kamar sayayya a kasuwa ko kuɗin makaranta, a Arewacin Najeriya.",
                        "quiz_id": None
                    }
                ]
            }
        ]
    },
    "online_banking_101": {
        "id": "online_banking_101",
        "title_en": "Online Banking Basics",
        "title_ha": "Asalin Banki na Kan Layi",
        "description_en": "Learn to use Nigerian banking apps securely for transactions and savings in Northern Nigeria.",
        "description_ha": "Koyi yadda ake amfani da manhajojin banki na Najeriya cikin aminci don cinikayya da ajiya a Arewacin Najeriya.",
        "title_key": "learning_hub_course_online_banking_title",
        "desc_key": "learning_hub_course_online_banking_desc",
        "is_premium": False,
        "roles": ["trader", "personal", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_online_banking_title",
                "title_en": "Online Banking Fundamentals",
                "title_ha": "Asalin Banki na Kan Layi",
                "lessons": [
                    {
                        "id": "online_banking_101-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_online_banking_security_title",
                        "title_en": "Secure Online Banking",
                        "title_ha": "Banki na Kan Layi Mai Aminci",
                        "content_type": "text",
                        "content_en": "Learn to use Nigerian banking apps securely, protecting your transactions from fraud in Northern Nigeria.",
                        "content_ha": "Koyi yadda ake amfani da manhajojin banki na Najeriya cikin aminci, kare cinikayyar ku daga zamba a Arewacin Najeriya.",
                        "quiz_id": None
                    }
                ]
            }
        ]
    },
    "financial_quiz": {
        "id": "financial_quiz",
        "title_en": "Financial Knowledge Quiz",
        "title_ha": "Jarabawar Ilimin Kudi",
        "description_en": "Test your financial knowledge with our comprehensive quiz and discover areas for improvement.",
        "description_ha": "Gwada ilimin ku na kudi da jarabawa mai cikakke kuma gano wuraren da za ku inganta.",
        "title_key": "learning_hub_course_financial_quiz_title",
        "desc_key": "learning_hub_course_financial_quiz_desc",
        "is_premium": False,
        "roles": ["trader", "personal", "agent"],
        "modules": [
            {
                "id": "module-1",
                "title_key": "learning_hub_module_quiz_title",
                "title_en": "Financial Assessment",
                "title_ha": "Ƙimar Kuɗi",
                "lessons": [
                    {
                        "id": "financial_quiz-module-1-lesson-1",
                        "title_key": "learning_hub_lesson_quiz_intro_title",
                        "title_en": "Quiz Introduction",
                        "title_ha": "Gabatarwar Jarabawa",
                        "content_type": "text",
                        "content_key": "learning_hub_lesson_quiz_intro_content",
                        "content_en": "This comprehensive quiz will help assess your current financial knowledge and identify areas where you can improve your financial literacy in a Northern Nigerian context.",
                        "content_ha": "Wannan jarabawar mai cikakke zata taimaka wajen tantance ilimin ku na kudi na yanzu kuma ta gano wuraren da za ku inganta ilimin ku na kudi a yanayin Arewacin Najeriya.",
                        "quiz_id": "quiz-financial-1"
                    }
                ]
            }
        ]
    }
}

quizzes_data = {
    "quiz-1-1": {
        "id": "quiz-1-1",
        "questions": [
            {
                "question_key": "learning_hub_quiz_income_q1",
                "question_en": "What is the most common source of income for most people in Northern Nigeria?",
                "question_ha": "Menene tushen kuɗin shiga da aka fi sani da shi ga yawancin mutane a Arewacin Najeriya?",
                "options_keys": [
                    "learning_hub_quiz_income_opt_salary",
                    "learning_hub_quiz_income_opt_business",
                    "learning_hub_quiz_income_opt_investment",
                    "learning_hub_quiz_income_opt_other"
                ],
                "options_en": ["Salary/Wages", "Business Income (e.g., market trading)", "Investment Returns", "Other Sources"],
                "options_ha": ["Albashi/Kuɗin Aiki", "Kuɗin Kasuwanci (misali, ciniki a kasuwa)", "Kuɗin Jari", "Sauran Tushen"],
                "answer_key": "learning_hub_quiz_income_opt_salary",
                "answer_en": "Salary/Wages",
                "answer_ha": "Albashi/Kuɗin Aiki"
            },
            {
                "question_key": "learning_hub_quiz_income_q2",
                "question_en": "What should you do with your income first?",
                "question_ha": "Menene yakamata ku ji da kuɗin shiga na farko?",
                "options_keys": [
                    "learning_hub_quiz_income_opt2_spend",
                    "learning_hub_quiz_income_opt2_save",
                    "learning_hub_quiz_income_opt2_invest",
                    "learning_hub_quiz_income_opt2_budget"
                ],
                "options_en": ["Spend on necessities (e.g., food, rent)", "Save everything", "Invest immediately", "Create a budget plan"],
                "options_ha": ["Kashe akan abubuwan bukata (misali, abinci, haya)", "Ajiye komai", "Saka hannun jari nan da nan", "Ƙirƙiri shirin kasafin kudi"],
                "answer_key": "learning_hub_quiz_income_opt2_budget",
                "answer_en": "Create a budget plan",
                "answer_ha": "Ƙirƙiri shirin kasafin kudi"
            }
        ]
    },
    "quiz-financial-1": {
        "id": "quiz-financial-1",
        "questions": [
            {
                "question_key": "learning_hub_quiz_financial_q1",
                "question_en": "What percentage of income should you ideally save for future goals like Hajj or education?",
                "question_ha": "Wace kashi na kuɗin shiga yakamata ku ajiye don maƙasudai na gaba kamar Hajji ko ilimi?",
                "options_keys": [
                    "learning_hub_quiz_financial_opt_a",
                    "learning_hub_quiz_financial_opt_b",
                    "learning_hub_quiz_financial_opt_c",
                    "learning_hub_quiz_financial_opt_d"
                ],
                "options_en": ["20%", "10%", "5%", "30%"],
                "options_ha": ["20%", "10%", "5%", "30%"],
                "answer_key": "learning_hub_quiz_financial_opt_a",
                "answer_en": "20%",
                "answer_ha": "20%"
            },
            {
                "question_key": "learning_hub_quiz_financial_q2",
                "question_en": "What is an emergency fund?",
                "question_ha": "Menene asusun gaggawa?",
                "options_keys": [
                    "learning_hub_quiz_financial_opt2_a",
                    "learning_hub_quiz_financial_opt2_b",
                    "learning_hub_quiz_financial_opt2_c",
                    "learning_hub_quiz_financial_opt2_d"
                ],
                "options_en": ["Money for vacations", "Money for unexpected expenses (e.g., medical emergencies)", "Money for investments", "Money for shopping"],
                "options_ha": ["Kuɗi don hutu", "Kuɗi don kuɗaɗen da ba a ji tsammani ba (misali, gaggawar likita)", "Kuɗi don jari", "Kuɗi don sayayya"],
                "answer_key": "learning_hub_quiz_financial_opt2_b",
                "answer_en": "Money for unexpected expenses",
                "answer_ha": "Kuɗi don kuɗaɗen da ba a ji tsammani ba"
            }
        ]
    },
    "quiz-savings-1": {
        "id": "quiz-savings-1",
        "questions": [
            {
                "question_key": "learning_hub_quiz_savings_q1",
                "question_en": "What is the 50/30/20 rule?",
                "question_ha": "Menene ƙa'idar 50/30/20?",
                "options_keys": [
                    "learning_hub_quiz_savings_opt_a",
                    "learning_hub_quiz_savings_opt_b",
                    "learning_hub_quiz_savings_opt_c",
                    "learning_hub_quiz_savings_opt_d"
                ],
                "options_en": ["50% needs, 30% wants, 20% savings", "50% savings, 30% needs, 20% wants", "50% wants, 30% savings, 20% needs", "50% investments, 30% savings, 20% spending"],
                "options_ha": ["50% buƙatu, 30% son rai, 20% ajiya", "50% ajiya, 30% buƙatu, 20% son rai", "50% son rai, 30% ajiya, 20% buƙatu", "50% jari, 30% ajiya, 20% kashewa"],
                "answer_key": "learning_hub_quiz_savings_opt_a",
                "answer_en": "50% needs, 30% wants, 20% savings",
                "answer_ha": "50% buƙatu, 30% son rai, 20% ajiya"
            }
        ]
    },
    "quiz-tax-reforms-2025": {
        "id": "quiz-tax-reforms-2025",
        "questions": [
            {
                "question_key": "learning_hub_quiz_tax_reforms_q1",
                "question_en": "What is the new rent relief threshold for PIT in 2025?",
                "question_ha": "Menene sabon ƙofa na tallafin haya don PIT a 2025?",
                "options_keys": [
                    "learning_hub_quiz_tax_reforms_opt1_a",
                    "learning_hub_quiz_tax_reforms_opt1_b",
                    "learning_hub_quiz_tax_reforms_opt1_c",
                    "learning_hub_quiz_tax_reforms_opt1_d"
                ],
                "options_en": ["₦100,000", "₦200,000", "₦500,000", "None"],
                "options_ha": ["₦100,000", "₦200,000", "₦500,000", "Babu"],
                "answer_key": "learning_hub_quiz_tax_reforms_opt1_b",
                "answer_en": "₦200,000",
                "answer_ha": "₦200,000"
            },
            {
                "question_key": "learning_hub_quiz_tax_reforms_q2",
                "question_en": "A business earning ₦30,000,000 yearly will pay what CIT rate in 2025?",
                "question_ha": "Kasuwanci da ke samun ₦30,000,000 a shekara zai biya wane ƙimar CIT a 2025?",
                "options_keys": [
                    "learning_hub_quiz_tax_reforms_opt2_a",
                    "learning_hub_quiz_tax_reforms_opt2_b",
                    "learning_hub_quiz_tax_reforms_opt2_c",
                    "learning_hub_quiz_tax_reforms_opt2_d"
                ],
                "options_en": ["0%", "20%", "25%", "30%"],
                "options_ha": ["0%", "20%", "25%", "30%"],
                "answer_key": "learning_hub_quiz_tax_reforms_opt2_a",
                "answer_en": "0%",
                "answer_ha": "0%"
            },
            {
                "question_key": "learning_hub_quiz_tax_reforms_q3",
                "question_en": "Which of these items is now VAT-exempt in 2025?",
                "question_ha": "Wanne daga cikin waɗannan abubuwan yanzu ba a saka VAT a 2025?",
                "options_keys": [
                    "learning_hub_quiz_tax_reforms_opt3_a",
                    "learning_hub_quiz_tax_reforms_opt3_b",
                    "learning_hub_quiz_tax_reforms_opt3_c",
                    "learning_hub_quiz_tax_reforms_opt3_d"
                ],
                "options_en": ["Soft drinks", "Healthcare", "Designer clothes", "Luxury cars"],
                "options_ha": ["Abin sha mai laushi", "Kiwon lafiya", "Tufafi na musamman", "Motoci na alatu"],
                "answer_key": "learning_hub_quiz_tax_reforms_opt3_b",
                "answer_en": "Healthcare",
                "answer_ha": "Kiwon lafiya"
            },
            {
                "question_key": "learning_hub_quiz_tax_reforms_q4",
                "question_en": "What tax benefit do large companies enjoy in 2025?",
                "question_ha": "Wane fa'ida ta haraji ne manyan kamfanoni ke ji a 2025?",
                "options_keys": [
                    "learning_hub_quiz_tax_reforms_opt4_a",
                    "learning_hub_quiz_tax_reforms_opt4_b",
                    "learning_hub_quiz_tax_reforms_opt4_c",
                    "learning_hub_quiz_tax_reforms_opt4_d"
                ],
                "options_en": ["Flat rate of 35%", "Exemption from tax", "Reduced VAT", "Reduced CIT to 27.5%, later 25%"],
                "options_ha": ["Ƙimar yau da kullun na 35%", "Keɓewa daga haraji", "Rage VAT", "Rage CIT zuwa 27.5%, daga baya 25%"],
                "answer_key": "learning_hub_quiz_tax_reforms_opt4_d",
                "answer_en": "Reduced CIT to 27.5%, later 25%",
                "answer_ha": "Rage CIT zuwa 27.5%, daga baya 25%"
            }
        ]
    },
    "quiz-digital-foundations-3-1": {
        "id": "quiz-digital-foundations-3-1",
        "questions": [
            {
                "question_key": "learning_hub_quiz_digital_q1",
                "question_en": "What can AI tools like ChatGPT help you with in Northern Nigeria?",
                "question_ha": "Menene kayan aikin AI kamar ChatGPT zasu iya taimaka muku da shi a Arewacin Najeriya?",
                "options_keys": [
                    "learning_hub_quiz_digital_opt1_a",
                    "learning_hub_quiz_digital_opt1_b",
                    "learning_hub_quiz_digital_opt1_c",
                    "learning_hub_quiz_digital_opt1_d"
                ],
                "options_en": ["Budgeting for household expenses", "Building a computer", "Driving a car", "Cooking meals"],
                "options_ha": ["Tsarin kudi don kuɗaɗen gida", "Gina kwamfuta", "Tukin mota", "Dafa abinci"],
                "answer_key": "learning_hub_quiz_digital_opt1_a",
                "answer_en": "Budgeting for household expenses",
                "answer_ha": "Tsarin kudi don kuɗaɗen gida"
            }
        ]
    },
    "quiz-islamic-finance-1": {
        "id": "quiz-islamic-finance-1",
        "questions": [
            {
                "question_key": "learning_hub_quiz_islamic_finance_q1",
                "question_en": "Which investment option is considered Halal in Islamic finance?",
                "question_ha": "Wane zaɓin jari ne ake ɗauka a matsayin Halal a cikin kuɗin Musulunci?",
                "options_keys": [
                    "learning_hub_quiz_islamic_finance_opt1_a",
                    "learning_hub_quiz_islamic_finance_opt1_b",
                    "learning_hub_quiz_islamic_finance_opt1_c",
                    "learning_hub_quiz_islamic_finance_opt1_d"
                ],
                "options_en": ["Sukuk", "Interest-based bonds", "Speculative trading", "Alcohol production"],
                "options_ha": ["Sukuk", "Bonds na riba", "Ciniki na hasashe", "Samar da barasa"],
                "answer_key": "learning_hub_quiz_islamic_finance_opt1_a",
                "answer_en": "Sukuk",
                "answer_ha": "Sukuk"
            }
        ]
    },
    "quiz-marketing-1": {
        "id": "quiz-marketing-1",
        "questions": [
            {
                "question_key": "learning_hub_quiz_marketing_q1",
                "question_en": "Which platform is effective for marketing in Northern Nigerian markets?",
                "question_ha": "Wane dandamali ne mai inganci don tallace-tallace a kasuwannin Arewacin Najeriya?",
                "options_keys": [
                    "learning_hub_quiz_marketing_opt1_a",
                    "learning_hub_quiz_marketing_opt1_b",
                    "learning_hub_quiz_marketing_opt1_c",
                    "learning_hub_quiz_marketing_opt1_d"
                ],
                "options_en": ["WhatsApp", "Television ads", "Billboards", "Newspapers"],
                "options_ha": ["WhatsApp", "Tallan talabijin", "Allunan talla", "Jaridu"],
                "answer_key": "learning_hub_quiz_marketing_opt1_a",
                "answer_en": "WhatsApp",
                "answer_ha": "WhatsApp"
            }
        ]
    },
    "reality_check_quiz": {
        "id": "reality_check_quiz",
        "questions": [
            {
                "question_key": "learning_hub_quiz_q1",
                "question_en": "What is a web browser?",
                "question_ha": "Menene mai bincike na yanar gizo?",
                "options_keys": [
                    "learning_hub_quiz_q1_a",
                    "learning_hub_quiz_q1_b"
                ],
                "options_en": ["A program to browse the internet", "A type of computer hardware"],
                "options_ha": ["Shiri don binciken intanet", "Nau'in kayan aikin kwamfuta"],
                "answer_key": "learning_hub_quiz_q1_a",
                "answer_en": "A program to browse the internet",
                "answer_ha": "Shiri don binciken intanet"
            },
            {
                "question_key": "learning_hub_quiz_q2",
                "question_en": "How do you save a file?",
                "question_ha": "Yadda ake ajiye fayil?",
                "options_keys": [
                    "learning_hub_quiz_q2_a",
                    "learning_hub_quiz_q2_b"
                ],
                "options_en": ["Click File > Save in an application", "Send it to an email"],
                "options_ha": ["Danna Fayil > Ajiye a cikin manhaja", "Aika shi zuwa imel"],
                "answer_key": "learning_hub_quiz_q2_a",
                "answer_en": "Click File > Save in an application",
                "answer_ha": "Danna Fayil > Ajiye a cikin manhaja"
            }
        ]
    }
}

def init_learning_materials(app):
    """Initialize learning materials (courses and quizzes) in MongoDB."""
    with app.app_context():
        logger.info("Initializing learning materials storage.", extra={'session_id': 'no-request-context'})
        try:
            db = get_mongo_db()
            existing_courses = list(db.learning_materials.find({'type': 'course'}))
            existing_course_ids = {course['id'] for course in existing_courses}
            logger.info(f"Found {len(existing_courses)} existing courses: {existing_course_ids}", extra={'session_id': 'no-request-context'})
            
            # Prepare default courses, skipping duplicates
            default_courses = [
                {
                    'type': 'course',
                    'id': course['id'],
                    '_id': ObjectId(),
                    'title_key': course['title_key'],
                    'title_en': course['title_en'],
                    'title_ha': course['title_ha'],
                    'description_en': course['description_en'],
                    'description_ha': course['description_ha'],
                    'is_premium': course.get('is_premium', False),
                    'roles': course.get('roles', []),
                    'modules': course.get('modules', []),
                    'created_at': datetime.utcnow()
                } for course in courses_data.values() if course['id'] not in existing_course_ids
            ]
            
            # Initialize quizzes
            existing_quizzes = list(db.learning_materials.find({'type': 'quiz'}))
            existing_quiz_ids = {quiz['id'] for quiz in existing_quizzes}
            default_quizzes = [
                {
                    'type': 'quiz',
                    'id': quiz['id'],
                    '_id': ObjectId(),
                    'questions': quiz['questions'],
                    'created_at': datetime.utcnow()
                } for quiz in quizzes_data.values() if quiz['id'] not in existing_quiz_ids
            ]
            
            if default_courses:
                db.learning_materials.insert_many(default_courses)
                logger.info(f"Initialized learning_materials with {len(default_courses)} default courses", extra={'session_id': 'no-request-context'})
            else:
                logger.info("No new courses to initialize; all default courses already exist", extra={'session_id': 'no-request-context'})
                
            if default_quizzes:
                db.learning_materials.insert_many(default_quizzes)
                logger.info(f"Initialized learning_materials with {len(default_quizzes)} default quizzes", extra={'session_id': 'no-request-context'})
            else:
                logger.info("No new quizzes to initialize; all default quizzes already exist", extra={'session_id': 'no-request-context'})
        except Exception as e:
            logger.error(f"Error initializing learning materials: {str(e)}", exc_info=True, extra={'session_id': 'no-request-context'})
            raise

def get_progress():
    """Retrieve learning progress from MongoDB with caching."""
    try:
        filter_kwargs = {} if current_user.is_authenticated and hasattr(current_user, 'is_admin') and current_user.is_admin else {'user_id': current_user.id} if current_user.is_authenticated else {'session_id': session.get('sid')}
        progress_records = get_mongo_db().learning_materials.find(filter_kwargs)
        progress = {}
        for record in progress_records:
            try:
                course_id = record.get('course_id')
                if not course_id:
                    logger.warning(f"Invalid progress record, missing course_id: {record}", extra={'session_id': session.get('sid', 'no-session-id')})
                    continue
                progress[course_id] = {
                    'lessons_completed': record.get('lessons_completed', []),
                    'quiz_scores': record.get('quiz_scores', {}),
                    'current_lesson': record.get('current_lesson'),
                    'coins_earned': record.get('coins_earned', 0),
                    'badges_earned': record.get('badges_earned', [])
                }
            except Exception as e:
                logger.error(f"Error parsing progress record for course {record.get('course_id', 'unknown')}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return progress
    except Exception as e:
        logger.error(f"Error retrieving progress from MongoDB: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        return {}

def save_course_progress(course_id, course_progress):
    """Save course progress to MongoDB with validation."""
    try:
        if 'sid' not in session:
            from session_utils import create_anonymous_session
            create_anonymous_session()
            session.permanent = True
            session.modified = True
        if not isinstance(course_id, str) or not isinstance(course_progress, dict):
            logger.error(f"Invalid course_id or course_progress: course_id={course_id}, course_progress={course_progress}", extra={'session_id': session.get('sid', 'no-session-id')})
            return
        filter_kwargs = {'course_id': course_id} if current_user.is_authenticated and hasattr(current_user, 'is_admin') and current_user.is_admin else {'user_id': current_user.id, 'course_id': course_id} if current_user.is_authenticated else {'session_id': session['sid'], 'course_id': course_id}
        update_data = {
            '$set': {
                'type': 'progress',
                'user_id': current_user.id if current_user.is_authenticated else None,
                'session_id': session['sid'],
                'course_id': course_id,
                'lessons_completed': course_progress.get('lessons_completed', []),
                'quiz_scores': course_progress.get('quiz_scores', {}),
                'current_lesson': course_progress.get('current_lesson'),
                'coins_earned': course_progress.get('coins_earned', 0),
                'badges_earned': course_progress.get('badges_earned', []),
                'updated_at': datetime.utcnow()
            }
        }
        get_mongo_db().learning_materials.update_one(filter_kwargs, update_data, upsert=True)
        logger.info(f"Saved progress for course {course_id}", extra={'session_id': session['sid']})
    except Exception as e:
        logger.error(f"Error saving progress to MongoDB for course {course_id}: {str(e)}", extra={'session_id': session.get('sid', 'no-session-id')})
        raise

def course_lookup(course_id):
    """Retrieve course by ID with validation and fallback to in-memory data."""
    try:
        if course_id == 'all':
            return courses_data
        course = get_mongo_db().learning_materials.find_one({'type': 'course', 'id': course_id})
        if course and isinstance(course, dict) and 'modules' in course and isinstance(course['modules'], list):
            return course
        logger.warning(f"Course {course_id} not found in MongoDB or invalid, falling back to in-memory data", extra={'session_id': session.get('sid', 'no-session-id')})
        course = courses_data.get(course_id)
        if not course or not isinstance(course, dict) or 'modules' not in course or not isinstance(course['modules'], list):
            logger.error(f"Invalid course data for {course_id} in in-memory data", extra={'session_id': session.get('sid', 'no-session-id')})
            return None
        return course
    except Exception as e:
        logger.error(f"Error retrieving course {course_id}: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return None

def lesson_lookup(course, lesson_id):
    """Retrieve lesson and its module from a course."""
    try:
        if not course or not isinstance(course, dict) or 'modules' not in course:
            logger.error(f"Invalid course data for lesson lookup: {course}", extra={'session_id': session.get('sid', 'no-session-id')})
            return None, None
        for module in course['modules']:
            for lesson in module.get('lessons', []):
                if lesson.get('id') == lesson_id:
                    return lesson, module
        logger.warning(f"Lesson {lesson_id} not found in course", extra={'session_id': session.get('sid', 'no-session-id')})
        return None, None
    except Exception as e:
        logger.error(f"Error looking up lesson {lesson_id}: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return None, None
def to_dict_learning_progress(record):
    """Convert learning progress record to dictionary."""
    if not record:
        return {'course_id': None, 'progress': None}
    return {
        'id': str(record.get('_id', '')),
        'user_id': record.get('user_id', ''),
        'session_id': record.get('session_id', ''),
        'course_id': record.get('course_id', ''),
        'lessons_completed': record.get('lessons_completed', []),
        'quiz_scores': record.get('quiz_scores', {}),
        'current_lesson': record.get('current_lesson', ''),
        'coins_earned': record.get('coins_earned', 0),
        'badges_earned': record.get('badges_earned', []),
        'created_at': record.get('created_at'),
        'updated_at': record.get('updated_at')
    }
    
def calculate_progress_summary():
    """Calculate progress summary for display."""
    try:
        progress = get_progress()
        total_completed = 0
        total_quiz_scores = 0
        total_coins_earned = 0
        certificates_earned = 0
        badges_earned = []

        for course_id, course_progress in progress.items():
            course = course_lookup(course_id)
            if not course:
                continue
            lessons_completed = course_progress.get('lessons_completed', [])
            quiz_scores = course_progress.get('quiz_scores', {})
            total_coins_earned += clean_currency(course_progress.get('coins_earned', 0))
            badges_earned.extend(course_progress.get('badges_earned', []))

            total_completed += len(lessons_completed)
            total_quiz_scores += len(quiz_scores)

            # Count certificates (e.g., if all lessons in a course are completed)
            total_lessons = sum(len(module.get('lessons', [])) for module in course.get('modules', []))
            if len(lessons_completed) == total_lessons:
                certificates_earned += 1

        return (
            progress,
            total_completed,
            total_quiz_scores,
            certificates_earned,
            format_currency(total_coins_earned, currency='NGN'),
            badges_earned
        )
    except Exception as e:
        logger.error(f"Error calculating progress summary: {str(e)}", exc_info=True, extra={'session_id': session.get('sid', 'no-session-id')})
        return {}, 0, 0, 0, format_currency(0, currency='NGN'), []
