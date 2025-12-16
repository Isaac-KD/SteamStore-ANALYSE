import pandas as pd

def read_description(path):
    # Lire le fichier JSONL
    df = pd.read_json(path, lines=True)
    
    # Filtrer les lignes avec une description courte non vide
    df = df[df['description_courte'].notna() & (df['description_courte'].str.strip() != "")]
    
    # Ne garder que les colonnes description_courte et game_id
    df = df[['app_id', 'description_courte']].reset_index(drop=True)
    
    return df

def save_description_pkl(descriptions, path):
    descriptions.to_pickle(path)
    
if "_name_" == "_main_":
    df = read_description("data_collected/valide_data.jsonl")
    save_description_pkl(df,"embedding/description.pkl")
    df = pd.read_pickle("embedding/description.pkl")
    print(df.head())