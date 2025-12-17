import dtale
import pandas as pd
import webbrowser

df = pd.read_parquet("data/train.parquet")
instance = dtale.show(df)

webbrowser.open(instance._url)

print("D-Tale running at:", instance._url)
input("Appuie sur Entrée pour fermer D-Tale...")
