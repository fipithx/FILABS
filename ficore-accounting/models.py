from datetime import datetime
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, DuplicateKeyError, OperationFailure
from werkzeug.security import generate_password_hash
from bson import ObjectId
import os
import logging
import uuid
import time
from translations import trans
from utils import get_mongo_db, log_tool_usage, logger # Use SessionAdapter logger from utils
from functools import lru_cache
import traceback

# Configure logger for the application
logger = logging.getLogger('ficore_app')
logger.setLevel(logging.INFO)

def get_db():
    """
    Get MongoDB database connection using the global client from utils.py.
    
    Returns:
        Database object
    """
    try:
        db = get_mongo_db()
        logger.info(f"Successfully connected to MongoDB database: {db.name}", extra={'session_id': 'no-session-id'})
        return db
    except Exception as e:
        logger.error(f"Error connecting to database: {str(e)}", exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def initialize_app_data(app):
    """
    Initialize MongoDB collections, indexes, and learning materials (courses and quizzes).
    
    Args:
        app: Flask application instance
    """
    max_retries = 3
    retry_delay = 1
    
    with app.app_context():
        for attempt in range(max_retries):
            try:
                db = get_db()
                db.command('ping')
                logger.info(f"Attempt {attempt + 1}/{max_retries} - {trans('general_database_connection_established', default='MongoDB connection established')}", 
                           extra={'session_id': 'no-session-id'})
                break
            except (ConnectionFailure, ServerSelectionTimeoutError) as e:
                logger.error(f"Failed to initialize database (attempt {attempt + 1}/{max_retries}): {str(e)}", 
                            exc_info=True, extra={'session_id': 'no-session-id'})
                if attempt == max_retries - 1:
                    raise RuntimeError(trans('general_database_connection_failed', default='MongoDB connection failed after max retries'))
                time.sleep(retry_delay)
        
        try:
            db_instance = get_db()
            logger.info(f"MongoDB database: {db_instance.name}", extra={'session_id': 'no-session-id'})
            collections = db_instance.list_collection_names()
            
            collection_schemas = {
                'users': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['_id', 'email', 'password_hash', 'role'],
                            'properties': {
                                '_id': {'bsonType': 'string'},
                                'email': {'bsonType': 'string', 'pattern': r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'},
                                'password_hash': {'bsonType': 'string'},
                                'role': {'enum': ['personal', 'trader', 'agent', 'admin', 'civil_servant', 'nysc']},
                                'coin_balance': {'bsonType': 'int', 'minimum': 0},
                                'language': {'enum': ['en', 'ha']},
                                'created_at': {'bsonType': 'date'},
                                'display_name': {'bsonType': ['string', 'null']},
                                'is_admin': {'bsonType': 'bool'},
                                'setup_complete': {'bsonType': 'bool'},
                                'reset_token': {'bsonType': ['string', 'null']},
                                'reset_token_expiry': {'bsonType': ['date', 'null']},
                                'otp': {'bsonType': ['string', 'null']},
                                'otp_expiry': {'bsonType': ['date', 'null']},
                                'business_details': {
                                    'bsonType': ['object', 'null'],
                                    'properties': {
                                        'name': {'bsonType': 'string'},
                                        'address': {'bsonType': 'string'},
                                        'industry': {'bsonType': 'string'},
                                        'products_services': {'bsonType': 'string'},
                                        'phone_number': {'bsonType': 'string'}
                                    }
                                },
                                'personal_details': {
                                    'bsonType': ['object', 'null'],
                                    'properties': {
                                        'first_name': {'bsonType': 'string'},
                                        'last_name': {'bsonType': 'string'},
                                        'phone_number': {'bsonType': 'string'},
                                        'address': {'bsonType': 'string'}
                                    }
                                },
                                'agent_details': {
                                    'bsonType': ['object', 'null'],
                                    'properties': {
                                        'agent_name': {'bsonType': 'string'},
                                        'agent_id': {'bsonType': 'string'},
                                        'area': {'bsonType': 'string'},
                                        'role': {'bsonType': 'string'},
                                        'email': {'bsonType': 'string'},
                                        'phone': {'bsonType': 'string'}
                                    }
                                }
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('email', ASCENDING)], 'unique': True},
                        {'key': [('reset_token', ASCENDING)], 'sparse': True},
                        {'key': [('role', ASCENDING)]}
                    ]
                },
                'records': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'type', 'name', 'amount_owed'],
                            'properties': {
                                'user_id': {'bsonType': 'string'},
                                'type': {'enum': ['debtor', 'creditor']},
                                'name': {'bsonType': 'string'},
                                'contact': {'bsonType': ['string', 'null']},
                                'amount_owed': {'bsonType': 'number', 'minimum': 0},
                                'description': {'bsonType': ['string', 'null']},
                                'reminder_count': {'bsonType': 'int', 'minimum': 0},
                                'created_at': {'bsonType': 'date'},
                                'updated_at': {'bsonType': ['date', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING), ('type', ASCENDING)]},
                        {'key': [('created_at', DESCENDING)]}
                    ]
                },
                'cashflows': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'type', 'party_name', 'amount'],
                            'properties': {
                                'user_id': {'bsonType': 'string'},
                                'type': {'enum': ['receipt', 'payment']},
                                'party_name': {'bsonType': 'string'},
                                'amount': {'bsonType': 'number', 'minimum': 0},
                                'method': {'bsonType': ['string', 'null']},
                                'category': {'bsonType': ['string', 'null']},
                                'created_at': {'bsonType': 'date'},
                                'updated_at': {'bsonType': ['date', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING), ('type', ASCENDING)]},
                        {'key': [('created_at', DESCENDING)]}
                    ]
                },
                'inventory': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'item_name', 'qty', 'unit', 'buying_price', 'selling_price'],
                            'properties': {
                                'user_id': {'bsonType': 'string'},
                                'item_name': {'bsonType': 'string'},
                                'qty': {'bsonType': 'int', 'minimum': 0},
                                'unit': {'bsonType': 'string'},
                                'buying_price': {'bsonType': 'number', 'minimum': 0},
                                'selling_price': {'bsonType': 'number', 'minimum': 0},
                                'threshold': {'bsonType': 'int', 'minimum': 0},
                                'created_at': {'bsonType': 'date'},
                                'updated_at': {'bsonType': ['date', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING)]},
                        {'key': [('item_name', ASCENDING)]}
                    ]
                },
                'coin_transactions': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'amount', 'type', 'date'],
                            'properties': {
                                'user_id': {'bsonType': 'string'},
                                'amount': {'bsonType': 'int'},
                                'type': {'enum': ['credit', 'spend', 'purchase', 'admin_credit']},
                                'ref': {'bsonType': ['string', 'null']},
                                'date': {'bsonType': 'date'},
                                'facilitated_by_agent': {'bsonType': ['string', 'null']},
                                'payment_method': {'bsonType': ['string', 'null']},
                                'cash_amount': {'bsonType': ['number', 'null']},
                                'notes': {'bsonType': ['string', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING)]},
                        {'key': [('date', DESCENDING)]}
                    ]
                },
                'audit_logs': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['admin_id', 'action', 'timestamp'],
                            'properties': {
                                'admin_id': {'bsonType': 'string'},
                                'action': {'bsonType': 'string'},
                                'details': {'bsonType': ['object', 'null']},
                                'timestamp': {'bsonType': 'date'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('admin_id', ASCENDING)]},
                        {'key': [('timestamp', DESCENDING)]}
                    ]
                },
                'agents': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['_id', 'status', 'created_at'],
                            'properties': {
                                '_id': {'bsonType': 'string', 'pattern': r'^[A-Z0-9]{8}$'},
                                'status': {'enum': ['active', 'inactive']},
                                'created_at': {'bsonType': 'date'},
                                'updated_at': {'bsonType': ['date', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('status', ASCENDING)]}
                    ]
                },
                'tax_rates': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['role', 'min_income', 'max_income', 'rate', 'description'],
                            'properties': {
                                'role': {'enum': ['personal', 'trader', 'agent', 'company', 'civil_servant', 'nysc']},
                                'min_income': {'bsonType': 'number'},
                                'max_income': {'bsonType': 'number'},
                                'rate': {'bsonType': 'number', 'minimum': 0, 'maximum': 1},
                                'description': {'bsonType': 'string'},
                                'session_id': {'bsonType': ['string', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('role', ASCENDING)]},
                        {'key': [('min_income', ASCENDING)]},
                        {'key': [('session_id', ASCENDING)]}
                    ]
                },
                'payment_locations': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['name', 'address', 'contact'],
                            'properties': {
                                'name': {'bsonType': 'string'},
                                'address': {'bsonType': 'string'},
                                'contact': {'bsonType': 'string'},
                                'coordinates': {
                                    'bsonType': ['object', 'null'],
                                    'properties': {
                                        'lat': {'bsonType': 'number'},
                                        'lng': {'bsonType': 'number'}
                                    }
                                }
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('name', ASCENDING)]}
                    ]
                },
                'tax_reminders': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'tax_type', 'due_date', 'amount', 'status', 'created_at'],
                            'properties': {
                                'user_id': {'bsonType': 'string'},
                                'session_id': {'bsonType': ['string', 'null']},
                                'tax_type': {'bsonType': 'string'},
                                'due_date': {'bsonType': 'date'},
                                'amount': {'bsonType': 'number', 'minimum': 0},
                                'status': {'enum': ['pending', 'paid', 'overdue']},
                                'created_at': {'bsonType': 'date'},
                                'updated_at': {'bsonType': ['date', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING)]},
                        {'key': [('session_id', ASCENDING)]},
                        {'key': [('due_date', ASCENDING)]}
                    ]
                },
                'feedback': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'tool_name', 'rating', 'timestamp'],
                            'properties': {
                                'user_id': {'bsonType': ['string', 'null']},
                                'session_id': {'bsonType': ['string', 'null']},
                                'tool_name': {'bsonType': 'string'},
                                'rating': {'bsonType': 'int', 'minimum': 1, 'maximum': 5},
                                'comment': {'bsonType': ['string', 'null']},
                                'timestamp': {'bsonType': 'date'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING)]},
                        {'key': [('session_id', ASCENDING)]},
                        {'key': [('timestamp', DESCENDING)]}
                    ]
                },
                'tool_usage': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['tool_name', 'timestamp'],
                            'properties': {
                                'tool_name': {'bsonType': 'string'},
                                'user_id': {'bsonType': ['string', 'null']},
                                'session_id': {'bsonType': ['string', 'null']},
                                'action': {'bsonType': ['string', 'null']},
                                'timestamp': {'bsonType': 'date'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('tool_name', ASCENDING)]},
                        {'key': [('timestamp', DESCENDING)]}
                    ]
                },
                'news_articles': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['title', 'content', 'source_type', 'published_at'],
                            'properties': {
                                'title': {'bsonType': 'string'},
                                'content': {'bsonType': 'string'},
                                'source_type': {'bsonType': 'string'},
                                'published_at': {'bsonType': 'date'},
                                'is_verified': {'bsonType': 'bool'},
                                'is_active': {'bsonType': 'bool'},
                                'session_id': {'bsonType': ['string', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('published_at', DESCENDING)]},
                        {'key': [('session_id', ASCENDING)]}
                    ]
                },
                'financial_health_scores': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'score', 'status', 'created_at'],
                            'properties': {
                                'user_id': {'bsonType': 'string'},
                                'session_id': {'bsonType': ['string', 'null']},
                                'score': {'bsonType': 'number', 'minimum': 0, 'maximum': 100},
                                'status': {'bsonType': 'string'},
                                'debt_to_income': {'bsonType': 'number'},
                                'savings_rate': {'bsonType': 'number'},
                                'interest_burden': {'bsonType': 'number'},
                                'badges': {'bsonType': ['array', 'null']},
                                'created_at': {'bsonType': 'date'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING), ('created_at', DESCENDING)]},
                        {'key': [('session_id', ASCENDING), ('created_at', DESCENDING)]}
                    ]
                },
                'budgets': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'income', 'fixed_expenses', 'variable_expenses', 'created_at'],
                            'properties': {
                                'user_id': {'bsonType': 'string'},
                                'session_id': {'bsonType': ['string', 'null']},
                                'income': {'bsonType': 'number', 'minimum': 0},
                                'fixed_expenses': {'bsonType': 'number', 'minimum': 0},
                                'variable_expenses': {'bsonType': 'number', 'minimum': 0},
                                'savings_goal': {'bsonType': 'number', 'minimum': 0},
                                'surplus_deficit': {'bsonType': 'number'},
                                'housing': {'bsonType': 'number', 'minimum': 0},
                                'food': {'bsonType': 'number', 'minimum': 0},
                                'transport': {'bsonType': 'number', 'minimum': 0},
                                'dependents': {'bsonType': 'number', 'minimum': 0},
                                'miscellaneous': {'bsonType': 'number', 'minimum': 0},
                                'others': {'bsonType': 'number', 'minimum': 0},
                                'created_at': {'bsonType': 'date'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING), ('created_at', DESCENDING)]},
                        {'key': [('session_id', ASCENDING), ('created_at', DESCENDING)]}
                    ]
                },
                'bills': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'bill_name', 'amount', 'due_date', 'status'],
                            'properties': {
                                'user_id': {'bsonType': 'string'},
                                'session_id': {'bsonType': ['string', 'null']},
                                'bill_name': {'bsonType': 'string'},
                                'amount': {'bsonType': 'number', 'minimum': 0},
                                'due_date': {'bsonType': 'date'},
                                'frequency': {'bsonType': ['string', 'null']},
                                'category': {'bsonType': ['string', 'null']},
                                'status': {'enum': ['pending', 'paid', 'overdue']},
                                'send_notifications': {'bsonType': 'bool'},
                                'send_email': {'bsonType': 'bool'},
                                'send_sms': {'bsonType': 'bool'},
                                'send_whatsapp': {'bsonType': 'bool'},
                                'reminder_days': {'bsonType': ['int', 'null']},
                                'user_email': {'bsonType': ['string', 'null']},
                                'user_phone': {'bsonType': ['string', 'null']},
                                'first_name': {'bsonType': ['string', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING), ('due_date', ASCENDING)]},
                        {'key': [('session_id', ASCENDING), ('due_date', ASCENDING)]},
                        {'key': [('status', ASCENDING)]}
                    ]
                },
                'net_worth_data': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'total_assets', 'total_liabilities', 'net_worth', 'created_at'],
                            'properties': {
                                'user_id': {'bsonType': 'string'},
                                'session_id': {'bsonType': ['string', 'null']},
                                'cash_savings': {'bsonType': 'number', 'minimum': 0},
                                'investments': {'bsonType': 'number', 'minimum': 0},
                                'property': {'bsonType': 'number', 'minimum': 0},
                                'loans': {'bsonType': 'number', 'minimum': 0},
                                'total_assets': {'bsonType': 'number', 'minimum': 0},
                                'total_liabilities': {'bsonType': 'number', 'minimum': 0},
                                'net_worth': {'bsonType': 'number'},
                                'badges': {'bsonType': ['array', 'null']},
                                'created_at': {'bsonType': 'date'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING), ('created_at', DESCENDING)]},
                        {'key': [('session_id', ASCENDING), ('created_at', DESCENDING)]}
                    ]
                },
                'emergency_funds': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'monthly_expenses', 'current_savings', 'target_amount', 'created_at'],
                            'properties': {
                                'user_id': {'bsonType': 'string'},
                                'session_id': {'bsonType': ['string', 'null']},
                                'monthly_expenses': {'bsonType': 'number', 'minimum': 0},
                                'monthly_income': {'bsonType': 'number', 'minimum': 0},
                                'current_savings': {'bsonType': 'number', 'minimum': 0},
                                'risk_tolerance_level': {'bsonType': ['string', 'null']},
                                'dependents': {'bsonType': 'number', 'minimum': 0},
                                'timeline': {'bsonType': 'number', 'minimum': 0},
                                'recommended_months': {'bsonType': 'number', 'minimum': 0},
                                'target_amount': {'bsonType': 'number', 'minimum': 0},
                                'savings_gap': {'bsonType': 'number', 'minimum': 0},
                                'monthly_savings': {'bsonType': 'number', 'minimum': 0},
                                'percent_of_income': {'bsonType': ['number', 'null']},
                                'badges': {'bsonType': ['array', 'null']},
                                'created_at': {'bsonType': 'date'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING), ('created_at', DESCENDING)]},
                        {'key': [('session_id', ASCENDING), ('created_at', DESCENDING)]}
                    ]
                },
                'learning_materials': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['type'],
                            'properties': {
                                'type': {'enum': ['course', 'quiz', 'progress']},
                                'id': {'bsonType': 'string'},
                                'user_id': {'bsonType': ['string', 'null']},
                                'session_id': {'bsonType': ['string', 'null']},
                                'course_id': {'bsonType': ['string', 'null']},
                                'title_key': {'bsonType': ['string', 'null']},
                                'title_en': {'bsonType': ['string', 'null']},
                                'title_ha': {'bsonType': ['string', 'null']},
                                'description_en': {'bsonType': ['string', 'null']},
                                'description_ha': {'bsonType': ['string', 'null']},
                                'is_premium': {'bsonType': ['bool', 'null']},
                                'roles': {'bsonType': ['array', 'null']},
                                'modules': {'bsonType': ['array', 'null']},
                                'questions': {'bsonType': ['array', 'null']},
                                'lessons_completed': {'bsonType': ['array', 'null']},
                                'quiz_scores': {'bsonType': ['object', 'null']},
                                'current_lesson': {'bsonType': ['string', 'null']},
                                'coins_earned': {'bsonType': ['int', 'null'], 'minimum': 0},
                                'badges_earned': {'bsonType': ['array', 'null']},
                                'created_at': {'bsonType': 'date'},
                                'updated_at': {'bsonType': ['date', 'null']}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('type', ASCENDING)]},
                        {'key': [('user_id', ASCENDING), ('course_id', ASCENDING)]},
                        {'key': [('session_id', ASCENDING), ('course_id', ASCENDING)]}
                    ]
                },
                'quiz_responses': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'personality', 'score', 'created_at'],
                            'properties': {
                                'user_id': {'bsonType': 'string'},
                                'session_id': {'bsonType': ['string', 'null']},
                                'personality': {'bsonType': 'string'},
                                'score': {'bsonType': 'number', 'minimum': 0, 'maximum': 100},
                                'badges': {'bsonType': ['array', 'null']},
                                'insights': {'bsonType': ['array', 'null']},
                                'tips': {'bsonType': ['array', 'null']},
                                'created_at': {'bsonType': 'date'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING), ('created_at', DESCENDING)]},
                        {'key': [('session_id', ASCENDING), ('created_at', DESCENDING)]}
                    ]
                },
                'bill_reminders': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['user_id', 'notification_id', 'type', 'message', 'sent_at'],
                            'properties': {
                                'user_id': {'bsonType': 'string'},
                                'session_id': {'bsonType': ['string', 'null']},
                                'notification_id': {'bsonType': 'string'},
                                'type': {'enum': ['email', 'sms', 'whatsapp']},
                                'message': {'bsonType': 'string'},
                                'sent_at': {'bsonType': 'date'},
                                'read_status': {'bsonType': 'bool'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('user_id', ASCENDING), ('sent_at', DESCENDING)]},
                        {'key': [('session_id', ASCENDING), ('sent_at', DESCENDING)]}
                    ]
                },
                'sessions': {
                    'validator': {
                        '$jsonSchema': {
                            'bsonType': 'object',
                            'required': ['_id', 'data', 'expiration'],
                            'properties': {
                                '_id': {'bsonType': 'string'},
                                'data': {'bsonType': 'object'},
                                'expiration': {'bsonType': 'date'}
                            }
                        }
                    },
                    'indexes': [
                        {'key': [('expiration', ASCENDING)], 'expireAfterSeconds': 0}
                    ]
                }
            }
            
            for collection_name, config in collection_schemas.items():
                if collection_name not in collections:
                    try:
                        db_instance.create_collection(collection_name, validator=config.get('validator', {}))
                        logger.info(f"{trans('general_collection_created', default='Created collection')}: {collection_name}", 
                                   extra={'session_id': 'no-session-id'})
                    except OperationFailure as e:
                        logger.error(f"Failed to create collection {collection_name}: {str(e)}", 
                                    exc_info=True, extra={'session_id': 'no-session-id'})
                        raise
                
                existing_indexes = db_instance[collection_name].index_information()
                for index in config.get('indexes', []):
                    keys = index['key']
                    options = {k: v for k, v in index.items() if k != 'key'}
                    index_key_tuple = tuple(keys)
                    index_name = '_'.join(f"{k}_{v if isinstance(v, int) else str(v).replace(' ', '_')}" for k, v in keys)
                    index_exists = False
                    for existing_index_name, existing_index_info in existing_indexes.items():
                        if tuple(existing_index_info['key']) == index_key_tuple:
                            existing_options = {k: v for k, v in existing_index_info.items() if k not in ['key', 'v', 'ns']}
                            if existing_options == options:
                                logger.info(f"{trans('general_index_exists', default='Index already exists on')} {collection_name}: {keys} with options {options}", 
                                           extra={'session_id': 'no-session-id'})
                                index_exists = True
                            else:
                                try:
                                    db_instance[collection_name].drop_index(existing_index_name)
                                    logger.info(f"Dropped conflicting index {existing_index_name} on {collection_name}", 
                                               extra={'session_id': 'no-session-id'})
                                except OperationFailure as e:
                                    logger.error(f"Failed to drop index {existing_index_name} on {collection_name}: {str(e)}", 
                                                exc_info=True, extra={'session_id': 'no-session-id'})
                                    raise
                            break
                    if not index_exists:
                        try:
                            db_instance[collection_name].create_index(keys, name=index_name, **options)
                            logger.info(f"{trans('general_index_created', default='Created index on')} {collection_name}: {keys} with options {options}", 
                                       extra={'session_id': 'no-session-id'})
                        except OperationFailure as e:
                            if 'IndexKeySpecsConflict' in str(e):
                                logger.info(f"Attempting to resolve index conflict for {collection_name}: {index_name}", 
                                           extra={'session_id': 'no-session-id'})
                                db_instance[collection_name].drop_index(index_name)
                                db_instance[collection_name].create_index(keys, name=index_name, **options)
                                logger.info(f"Recreated index on {collection_name}: {keys} with options {options}", 
                                           extra={'session_id': 'no-session-id'})
                            else:
                                logger.error(f"Failed to create index on {collection_name}: {str(e)}", 
                                            exc_info=True, extra={'session_id': 'no-session-id'})
                                raise
            
            # Initialize agents
            agents_collection = db_instance.agents
            if agents_collection.count_documents({}) == 0:
                try:
                    agents_collection.insert_many([
                        {
                            '_id': 'AG123456',
                            'status': 'active',
                            'created_at': datetime.utcnow(),
                            'updated_at': datetime.utcnow()
                        }
                    ])
                    logger.info(trans('general_agents_initialized', default='Initialized agents in MongoDB'), 
                               extra={'session_id': 'no-session-id'})
                except OperationFailure as e:
                    logger.error(f"Failed to insert sample agents: {str(e)}", exc_info=True, extra={'session_id': 'no-session-id'})
                    raise
            
            # Initialize courses and quizzes (to be handled by learning hub's init_learning_materials)
            from learning_hub.models import init_learning_materials
            init_learning_materials(app)
            
        except Exception as e:
            logger.error(f"{trans('general_database_initialization_failed', default='Failed to initialize database')}: {str(e)}", 
                        exc_info=True, extra={'session_id': 'no-session-id'})
            raise

class User:
    def __init__(self, id, email, display_name=None, role='personal', username=None, is_admin=False, setup_complete=False, coin_balance=0, language='en', dark_mode=False):
        self.id = id
        self.email = email
        self.username = username or display_name or email.split('@')[0]
        self.role = role
        self.display_name = display_name or self.username
        self.is_admin = is_admin
        self.setup_complete = setup_complete
        self.coin_balance = coin_balance
        self.language = language
        self.dark_mode = dark_mode

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    def get(self, key, default=None):
        return getattr(self, key, default)

def create_user(db, user_data):
    """
    Create a new user in the users collection.
    
    Args:
        db: MongoDB database instance
        user_data: Dictionary containing user information
    
    Returns:
        User: Created user object
    """
    try:
        user_id = user_data.get('username', user_data['email'].split('@')[0]).lower()
        if 'password' in user_data:
            user_data['password_hash'] = generate_password_hash(user_data['password'])
        
        user_doc = {
            '_id': user_id,
            'email': user_data['email'].lower(),
            'password_hash': user_data.get('password_hash'),
            'role': user_data.get('role', 'personal'),
            'display_name': user_data.get('display_name', user_id),
            'is_admin': user_data.get('is_admin', False),
            'setup_complete': user_data.get('setup_complete', False),
            'coin_balance': user_data.get('coin_balance', 10),
            'language': user_data.get('lang', 'en'),
            'dark_mode': user_data.get('dark_mode', False),
            'created_at': user_data.get('created_at', datetime.utcnow()),
            'business_details': user_data.get('business_details'),
            'personal_details': user_data.get('personal_details'),
            'agent_details': user_data.get('agent_details')
        }
        
        db.users.insert_one(user_doc)
        logger.info(f"{trans('general_user_created', default='Created user with ID')}: {user_id}", 
                   extra={'session_id': 'no-session-id'})
        get_user.cache_clear()
        get_user_by_email.cache_clear()
        return User(
            id=user_id,
            email=user_doc['email'],
            username=user_id,
            role=user_doc['role'],
            display_name=user_doc['display_name'],
            is_admin=user_doc['is_admin'],
            setup_complete=user_doc['setup_complete'],
            coin_balance=user_doc['coin_balance'],
            language=user_doc['language'],
            dark_mode=user_doc['dark_mode']
        )
    except DuplicateKeyError as e:
        logger.error(f"{trans('general_user_creation_error', default='Error creating user')}: {trans('general_duplicate_key_error', default='Duplicate key error')} - {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise ValueError(trans('general_user_exists', default='User with this email or username already exists'))
    except Exception as e:
        logger.error(f"{trans('general_user_creation_error', default='Error creating user')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

@lru_cache(maxsize=128)
def get_user_by_email(db, email):
    """
    Retrieve a user by email from the users collection.
    
    Args:
        db: MongoDB database instance
        email: Email address of the user
    
    Returns:
        User: User object or None if not found
    """
    try:
        logger.debug(f"Calling get_user_by_email for email: {email}, stack: {''.join(traceback.format_stack()[-5:])}", 
                    extra={'session_id': 'no-session-id'})
        user_doc = db.users.find_one({'email': email.lower()})
        if user_doc:
            return User(
                id=user_doc['_id'],
                email=user_doc['email'],
                username=user_doc['_id'],
                role=user_doc.get('role', 'personal'),
                display_name=user_doc.get('display_name'),
                is_admin=user_doc.get('is_admin', False),
                setup_complete=user_doc.get('setup_complete', False),
                coin_balance=user_doc.get('coin_balance', 0),
                language=user_doc.get('language', 'en'),
                dark_mode=user_doc.get('dark_mode', False)
            )
        return None
    except Exception as e:
        logger.error(f"{trans('general_user_fetch_error', default='Error getting user by email')} {email}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

@lru_cache(maxsize=128)
def get_user(db, user_id):
    """
    Retrieve a user by ID from the users collection.
    
    Args:
        db: MongoDB database instance
        user_id: ID of the user
    
    Returns:
        User: User object or None if not found
    """
    try:
        logger.debug(f"Calling get_user for user_id: {user_id}, stack: {''.join(traceback.format_stack()[-5:])}", 
                    extra={'session_id': 'no-session-id'})
        user_doc = db.users.find_one({'_id': user_id})
        if user_doc:
            return User(
                id=user_doc['_id'],
                email=user_doc['email'],
                username=user_doc['_id'],
                role=user_doc.get('role', 'personal'),
                display_name=user_doc.get('display_name'),
                is_admin=user_doc.get('is_admin', False),
                setup_complete=user_doc.get('setup_complete', False),
                coin_balance=user_doc.get('coin_balance', 0),
                language=user_doc.get('language', 'en'),
                dark_mode=user_doc.get('dark_mode', False)
            )
        return None
    except Exception as e:
        logger.error(f"{trans('general_user_fetch_error', default='Error getting user by ID')} {user_id}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def get_agent(db, agent_id):
    """
    Retrieve an agent by ID from the agents collection.
    
    Args:
        db: MongoDB database instance
        agent_id: The agent ID to retrieve
    
    Returns:
        dict: Agent document or None if not found
    """
    try:
        agent_doc = db.agents.find_one({'_id': agent_id.upper()})
        if agent_doc:
            return {
                '_id': agent_doc['_id'],
                'status': agent_doc['status'],
                'created_at': agent_doc['created_at'],
                'updated_at': agent_doc.get('updated_at')
            }
        return None
    except Exception as e:
        logger.error(f"{trans('agents_fetch_error', default='Error getting agent by ID')} {agent_id}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def update_agent(db, agent_id, status):
    """
    Update an agent's status in the agents collection.
    
    Args:
        db: MongoDB database instance
        agent_id: The agent ID to update
        status: The new status ('active' or 'inactive')
    
    Returns:
        bool: True if updated, False if not found or no changes made
    """
    try:
        result = db.agents.update_one(
            {'_id': agent_id.upper()},
            {'$set': {'status': status, 'updated_at': datetime.utcnow()}}
        )
        if result.modified_count > 0:
            logger.info(f"{trans('agents_status_updated', default='Updated agent status for ID')}: {agent_id} to {status}", 
                       extra={'session_id': 'no-session-id'})
            return True
        return False
    except Exception as e:
        logger.error(f"{trans('agents_update_error', default='Error updating agent status for ID')} {agent_id}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def get_financial_health(db, filter_kwargs):
    """
    Retrieve financial health records based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria
    
    Returns:
        list: List of financial health records
    """
    try:
        return list(db.financial_health_scores.find(filter_kwargs).sort('created_at', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_financial_health_fetch_error', default='Error getting financial health')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def get_budgets(db, filter_kwargs):
    """
    Retrieve budget records based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria
    
    Returns:
        list: List of budget records
    """
    try:
        return list(db.budgets.find(filter_kwargs).sort('created_at', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_budgets_fetch_error', default='Error getting budgets')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def get_bills(db, filter_kwargs):
    """
    Retrieve bill records based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria
    
    Returns:
        list: List of bill records
    """
    try:
        return list(db.bills.find(filter_kwargs).sort('due_date', ASCENDING))
    except Exception as e:
        logger.error(f"{trans('general_bills_fetch_error', default='Error getting bills')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def get_net_worth(db, filter_kwargs):
    """
    Retrieve net worth records based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria
    
    Returns:
        list: List of net worth records
    """
    try:
        return list(db.net_worth_data.find(filter_kwargs).sort('created_at', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_net_worth_fetch_error', default='Error getting net worth')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def get_emergency_funds(db, filter_kwargs):
    """
    Retrieve emergency fund records based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria
    
    Returns:
        list: List of emergency fund records
    """
    try:
        return list(db.emergency_funds.find(filter_kwargs).sort('created_at', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_emergency_funds_fetch_error', default='Error getting emergency funds')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def get_quiz_results(db, filter_kwargs):
    """
    Retrieve quiz result records based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria
    
    Returns:
        list: List of quiz result records
    """
    try:
        return list(db.quiz_responses.find(filter_kwargs).sort('created_at', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_quiz_results_fetch_error', default='Error getting quiz results')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def get_news_articles(db, filter_kwargs):
    """
    Retrieve news article records based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria
    
    Returns:
        list: List of news article records
    """
    try:
        return list(db.news_articles.find(filter_kwargs).sort('published_at', DESCENDING))
    except Exception as e:
        logger.error(f"{trans('general_news_articles_fetch_error', default='Error getting news articles')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def get_tax_rates(db, filter_kwargs):
    """
    Retrieve tax rate records based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria
    
    Returns:
        list: List of tax rate records
    """
    try:
        return list(db.tax_rates.find(filter_kwargs).sort('min_income', ASCENDING))
    except Exception as e:
        logger.error(f"{trans('general_tax_rates_fetch_error', default='Error getting tax rates')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def get_payment_locations(db, filter_kwargs):
    """
    Retrieve payment location records based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria
    
    Returns:
        list: List of payment location records
    """
    try:
        return list(db.payment_locations.find(filter_kwargs).sort('name', ASCENDING))
    except Exception as e:
        logger.error(f"{trans('general_payment_locations_fetch_error', default='Error getting payment locations')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def get_tax_reminders(db, filter_kwargs):
    """
    Retrieve tax reminder records based on filter criteria.
    
    Args:
        db: MongoDB database instance
        filter_kwargs: Dictionary of filter criteria
    
    Returns:
        list: List of tax reminder records
    """
    try:
        return list(db.tax_reminders.find(filter_kwargs).sort('due_date', ASCENDING))
    except Exception as e:
        logger.error(f"{trans('general_tax_reminders_fetch_error', default='Error getting tax reminders')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def create_feedback(db, feedback_data):
    """
    Create a new feedback record in the feedback collection.
    
    Args:
        db: MongoDB database instance
        feedback_data: Dictionary containing feedback information
    """
    try:
        required_fields = ['user_id', 'tool_name', 'rating', 'timestamp']
        if not all(field in feedback_data for field in required_fields):
            raise ValueError(trans('general_missing_feedback_fields', default='Missing required feedback fields'))
        db.feedback.insert_one(feedback_data)
        logger.info(f"{trans('general_feedback_created', default='Created feedback record for tool')}: {feedback_data.get('tool_name')}", 
                   extra={'session_id': feedback_data.get('session_id', 'no-session-id')})
    except Exception as e:
        logger.error(f"{trans('general_feedback_creation_error', default='Error creating feedback')}: {str(e)}", 
                    exc_info=True, extra={'session_id': feedback_data.get('session_id', 'no-session-id')})
        raise

def log_tool_usage(db, tool_name, user_id=None, session_id=None, action=None):
    """
    Log tool usage in the tool_usage collection.
    
    Args:
        db: MongoDB database instance
        tool_name: Name of the tool used
        user_id: ID of the user (optional)
        session_id: Session ID (optional)
        action: Action performed (optional)
    """
    try:
        usage_data = {
            'tool_name': tool_name,
            'user_id': user_id,
            'session_id': session_id,
            'action': action,
            'timestamp': datetime.utcnow()
        }
        db.tool_usage.insert_one(usage_data)
        logger.info(f"{trans('general_tool_usage_logged', default='Logged tool usage')}: {tool_name} - {action}", 
                   extra={'session_id': session_id or 'no-session-id'})
    except Exception as e:
        logger.error(f"{trans('general_tool_usage_log_error', default='Error logging tool usage')}: {str(e)}", 
                    exc_info=True, extra={'session_id': session_id or 'no-session-id'})
        raise

def create_news_article(db, article_data):
    """
    Create a new news article in the news_articles collection.
    
    Args:
        db: MongoDB database instance
        article_data: Dictionary containing news article information
    
    Returns:
        str: ID of the created article
    """
    try:
        required_fields = ['title', 'content', 'source_type', 'published_at']
        if not all(field in article_data for field in required_fields):
            raise ValueError(trans('general_missing_news_fields', default='Missing required news article fields'))
        article_data.setdefault('is_verified', False)
        article_data.setdefault('is_active', True)
        result = db.news_articles.insert_one(article_data)
        logger.info(f"{trans('general_news_article_created', default='Created news article with ID')}: {result.inserted_id}", 
                   extra={'session_id': article_data.get('session_id', 'no-session-id')})
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"{trans('general_news_article_creation_error', default='Error creating news article')}: {str(e)}", 
                    exc_info=True, extra={'session_id': article_data.get('session_id', 'no-session-id')})
        raise

def create_tax_rate(db, tax_rate_data):
    """
    Create a new tax rate in the tax_rates collection.
    
    Args:
        db: MongoDB database instance
        tax_rate_data: Dictionary containing tax rate information
    
    Returns:
        str: ID of the created tax rate
    """
    try:
        required_fields = ['role', 'min_income', 'max_income', 'rate', 'description']
        if not all(field in tax_rate_data for field in required_fields):
            raise ValueError(trans('general_missing_tax_rate_fields', default='Missing required tax rate fields'))
        result = db.tax_rates.insert_one(tax_rate_data)
        logger.info(f"{trans('general_tax_rate_created', default='Created tax rate with ID')}: {result.inserted_id}", 
                   extra={'session_id': tax_rate_data.get('session_id', 'no-session-id')})
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"{trans('general_tax_rate_creation_error', default='Error creating tax rate')}: {str(e)}", 
                    exc_info=True, extra={'session_id': tax_rate_data.get('session_id', 'no-session-id')})
        raise

def create_payment_location(db, location_data):
    """
    Create a new payment location in the payment_locations collection.
    
    Args:
        db: MongoDB database instance
        location_data: Dictionary containing payment location information
    
    Returns:
        str: ID of the created payment location
    """
    try:
        required_fields = ['name', 'address', 'contact']
        if not all(field in location_data for field in required_fields):
            raise ValueError(trans('general_missing_location_fields', default='Missing required payment location fields'))
        result = db.payment_locations.insert_one(location_data)
        logger.info(f"{trans('general_payment_location_created', default='Created payment location with ID')}: {result.inserted_id}", 
                   extra={'session_id': 'no-session-id'})
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"{trans('general_payment_location_creation_error', default='Error creating payment location')}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

def create_tax_reminder(db, reminder_data):
    """
    Create a new tax reminder in the tax_reminders collection.
    
    Args:
        db: MongoDB database instance
        reminder_data: Dictionary containing tax reminder information
    
    Returns:
        str: ID of the created tax reminder
    """
    try:
        required_fields = ['user_id', 'tax_type', 'due_date', 'amount', 'status', 'created_at']
        if not all(field in reminder_data for field in required_fields):
            raise ValueError(trans('general_missing_reminder_fields', default='Missing required tax reminder fields'))
        result = db.tax_reminders.insert_one(reminder_data)
        logger.info(f"{trans('general_tax_reminder_created', default='Created tax reminder with ID')}: {result.inserted_id}", 
                   extra={'session_id': reminder_data.get('session_id', 'no-session-id')})
        return str(result.inserted_id)
    except Exception as e:
        logger.error(f"{trans('general_tax_reminder_creation_error', default='Error creating tax reminder')}: {str(e)}", 
                    exc_info=True, extra={'session_id': reminder_data.get('session_id', 'no-session-id')})
        raise

def update_tax_reminder(db, reminder_id, update_data):
    """
    Update a tax reminder in the tax_reminders collection.
    
    Args:
        db: MongoDB database instance
        reminder_id: The ID of the tax reminder to update
        update_data: Dictionary containing fields to update (e.g., status, amount, due_date)
    
    Returns:
        bool: True if updated, False if not found or no changes made
    """
    try:
        update_data['updated_at'] = datetime.utcnow()
        result = db.tax_reminders.update_one(
            {'_id': ObjectId(reminder_id)},
            {'$set': update_data}
        )
        if result.modified_count > 0:
            logger.info(f"{trans('general_tax_reminder_updated', default='Updated tax reminder with ID')}: {reminder_id}", 
                       extra={'session_id': 'no-session-id'})
            return True
        logger.info(f"{trans('general_tax_reminder_no_change', default='No changes made to tax reminder with ID')}: {reminder_id}", 
                   extra={'session_id': 'no-session-id'})
        return False
    except Exception as e:
        logger.error(f"{trans('general_tax_reminder_update_error', default='Error updating tax reminder with ID')} {reminder_id}: {str(e)}", 
                    exc_info=True, extra={'session_id': 'no-session-id'})
        raise

# Data conversion functions for backward compatibility
def to_dict_financial_health(record):
    """Convert financial health record to dictionary."""
    if not record:
        return {'score': None, 'status': None}
    return {
        'id': str(record.get('_id', '')),
        'score': record.get('score'),
        'status': record.get('status'),
        'debt_to_income': record.get('debt_to_income'),
        'savings_rate': record.get('savings_rate'),
        'interest_burden': record.get('interest_burden'),
        'badges': record.get('badges', []),
        'created_at': record.get('created_at')
    }

def to_dict_budget(record):
    """Convert budget record to dictionary."""
    if not record:
        return {'surplus_deficit': None, 'savings_goal': None}
    return {
        'id': str(record.get('_id', '')),
        'income': record.get('income', 0),
        'fixed_expenses': record.get('fixed_expenses', 0),
        'variable_expenses': record.get('variable_expenses', 0),
        'savings_goal': record.get('savings_goal', 0),
        'surplus_deficit': record.get('surplus_deficit', 0),
        'housing': record.get('housing', 0),
        'food': record.get('food', 0),
        'transport': record.get('transport', 0),
        'dependents': record.get('dependents', 0),
        'miscellaneous': record.get('miscellaneous', 0),
        'others': record.get('others', 0),
        'created_at': record.get('created_at')
    }

def to_dict_bill(record):
    """Convert bill record to dictionary."""
    if not record:
        return {'amount': None, 'status': None}
    return {
        'id': str(record.get('_id', '')),
        'bill_name': record.get('bill_name', ''),
        'amount': record.get('amount', 0),
        'due_date': record.get('due_date'),
        'frequency': record.get('frequency', ''),
        'category': record.get('category', ''),
        'status': record.get('status', ''),
        'send_notifications': record.get('send_notifications', False),
        'send_email': record.get('send_email', False),
        'send_sms': record.get('send_sms', False),
        'send_whatsapp': record.get('send_whatsapp', False),
        'reminder_days': record.get('reminder_days'),
        'user_email': record.get('user_email', ''),
        'user_phone': record.get('user_phone', ''),
        'first_name': record.get('first_name', '')
    }

def to_dict_net_worth(record):
    """Convert net worth record to dictionary."""
    if not record:
        return {'net_worth': None, 'total_assets': None}
    return {
        'id': str(record.get('_id', '')),
        'cash_savings': record.get('cash_savings', 0),
        'investments': record.get('investments', 0),
        'property': record.get('property', 0),
        'loans': record.get('loans', 0),
        'total_assets': record.get('total_assets', 0),
        'total_liabilities': record.get('total_liabilities', 0),
        'net_worth': record.get('net_worth', 0),
        'badges': record.get('badges', []),
        'created_at': record.get('created_at')
    }

def to_dict_emergency_fund(record):
    """Convert emergency fund record to dictionary."""
    if not record:
        return {'target_amount': None, 'savings_gap': None}
    return {
        'id': str(record.get('_id', '')),
        'monthly_expenses': record.get('monthly_expenses', 0),
        'monthly_income': record.get('monthly_income', 0),
        'current_savings': record.get('current_savings', 0),
        'risk_tolerance_level': record.get('risk_tolerance_level', ''),
        'dependents': record.get('dependents', 0),
        'timeline': record.get('timeline', 0),
        'recommended_months': record.get('recommended_months', 0),
        'target_amount': record.get('target_amount', 0),
        'savings_gap': record.get('savings_gap', 0),
        'monthly_savings': record.get('monthly_savings', 0),
        'percent_of_income': record.get('percent_of_income'),
        'badges': record.get('badges', []),
        'created_at': record.get('created_at')
    }

def to_dict_quiz_result(record):
    """Convert quiz result record to dictionary."""
    if not record:
        return {'personality': None, 'score': None}
    return {
        'id': str(record.get('_id', '')),
        'personality': record.get('personality', ''),
        'score': record.get('score', 0),
        'badges': record.get('badges', []),
        'insights': record.get('insights', []),
        'tips': record.get('tips', []),
        'created_at': record.get('created_at')
    }

def to_dict_news_article(record):
    """Convert news article record to dictionary."""
    if not record:
        return {'title': None, 'content': None}
    return {
        'id': str(record.get('_id', '')),
        'title': record.get('title', ''),
        'content': record.get('content', ''),
        'source_type': record.get('source_type', ''),
        'published_at': record.get('published_at'),
        'is_verified': record.get('is_verified', False),
        'is_active': record.get('is_active', True)
    }

def to_dict_tax_rate(record):
    """Convert tax rate record to dictionary."""
    if not record:
        return {'role': None, 'rate': None}
    return {
        'id': str(record.get('_id', '')),
        'role': record.get('role', ''),
        'min_income': record.get('min_income', 0),
        'max_income': record.get('max_income', 0),
        'rate': record.get('rate', 0),
        'description': record.get('description', '')
    }

def to_dict_payment_location(record):
    """Convert payment location record to dictionary."""
    if not record:
        return {'name': None, 'address': None}
    return {
        'id': str(record.get('_id', '')),
        'name': record.get('name', ''),
        'address': record.get('address', ''),
        'contact': record.get('contact', ''),
        'coordinates': record.get('coordinates')
    }

def to_dict_tax_reminder(record):
    """Convert tax reminder record to dictionary."""
    if not record:
        return {'tax_type': None, 'amount': None}
    return {
        'id': str(record.get('_id', '')),
        'user_id': record.get('user_id', ''),
        'session_id': record.get('session_id'),
        'tax_type': record.get('tax_type', ''),
        'due_date': record.get('due_date'),
        'amount': record.get('amount', 0),
        'status': record.get('status', ''),
        'created_at': record.get('created_at'),
        'updated_at': record.get('updated_at')
    }
