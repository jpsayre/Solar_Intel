# Solar Project

Step 1 (API Call)) IntialScript.py

    This calls SunroofBatchAPI.py and creates a csv with all of the API output

Step 2) Analyze_ProjectSunroof_Data.py

    This applies filters and qualifies matching roof segments

Step 3) Combine_Regrid_ProjectSunroof_Data.py

    Combines the Regrid data with the filtered Project Sunroof data

Step 4 (API Call)) download_map_images.py

    This goes through the qualified homes and downloads an image of them from Google Maps API

Step 5 (API Call)) analyze_solar_panels.py

    This uses the OpenAI API to analyze the downloaded images and categorize them as Yes/No to having solar installations

Step 6 (API Call)) AddSolarPanelClassifierColumn.py

    Joins the output of the AI onto the dataset

Step 7) FinalFilters.py

    Prepares the dataset for uploading