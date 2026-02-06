# Solar Project

Step 1 (API Call)) IntialScript.py

    TO DO: Will eventually need a script to go retry rows that returned an error

    This calls SunroofBatchAPI.py and creates a csv with all of the API output

Step 2) Analyze_ProjectSunroof_Data.py

    This applies filters and qualifies matching roof segments

Step 3) Combine_Regrid_ProjectSunroof_Data.py

    Combines the Regrid data with the filtered Project Sunroof data

Step 4 (API Call)) download_map_images.py
    
    This goes through the qualified homes and downloads an image of them from Google Maps API

Step 5 (API Call)) Analyze_Images_Add_Classifier.py

    This uses the OpenAI API to analyze the downloaded images and categorize them as Yes/No to having solar installations

Step 6) python src/view_solar_classifications.py

    Use this to manually confirm the AI classifications

Step 7) FinalFilters.py

    Prepares the dataset for delivery