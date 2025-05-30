from pymongo import MongoClient
import sys

def test_mongodb():
    try:
        # Connect to MongoDB
        client = MongoClient('mongodb://localhost:27017/')
        
        # Get database list to test connection
        db_list = client.list_database_names()
        print("Successfully connected to MongoDB!")
        print("Available databases:", db_list)
        
        # Test creating a document in nukem_bot database
        db = client['nukem_bot']
        collection = db['test_collection']
        test_doc = {"test": "connection"}
        result = collection.insert_one(test_doc)
        print("Successfully inserted test document with id:", result.inserted_id)
        
        # Clean up
        collection.delete_one({"test": "connection"})
        
    except Exception as e:
        print("Error connecting to MongoDB:", str(e))
        sys.exit(1)

if __name__ == "__main__":
    test_mongodb()
