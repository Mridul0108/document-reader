conversation_history=[]

def add_message(role,content,document=None):
    Max_messages=50
    
    message ={
        "role":role,
        "content":content,
        "document":document,
    }
    
    conversation_history.append(message)
    if len(conversation_history)>Max_messages:
                conversation_history.pop(0)



def get_history(document=None):
    if document is None:
        return conversation_history

    filtered_history=[
        message for message in conversation_history
         if message["document"]==document    
    ]
    return filtered_history