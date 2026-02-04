#Step 3

import pandas as pd

"""
After running the solar panel yes/no classifier in n8n, this script takes the classification column and merges it into the main dataset.
"""

location = 'Boulder_CO'

# Load datasets
A = pd.read_csv("/Users/jeffs/Projects/SolarProject/data/working/"+location+"_Regrid_joined_with_API.csv")  # must have columns: lat, lon
# B = pd.read_csv("/Users/jeffs/Projects/SolarProject/data/working/"+location+"_solar_classification_result.csv")  # must have 
B = pd.read_csv("/Users/jeffs/Projects/SolarProject/data/working/solar_panel_classifications.csv")  # must have 

B = B[['original_index','solar_panels']]

# Join B → A (left join keeps all rows from A)
A_joined = A.merge(
    B,
    on="original_index",
    how="left"
)


# Save result for any that don't have solar panels already

A_joined = A_joined[A_joined["solar_panels"]=="No"]
print('filter')
A_joined.to_csv("/Users/jeffs/Projects/SolarProject/data/working/"+location+"_Semi_Final_Data_w_Solar_Classifier.csv", index=False)
print('saved')