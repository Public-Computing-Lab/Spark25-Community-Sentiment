# Commands to Run

## Prerequisites
Make sure your MySQL container is running:
```bash
docker ps
```

If not running, start it:
```bash
docker run --name rethinkai-mysql -e MYSQL_ROOT_PASSWORD=MySecureRootPass123! -e MYSQL_DATABASE=rethinkai_db -e MYSQL_USER=rethinkai_user -e MYSQL_PASSWORD=MySecureUserPass123! -p 3306:3306 -v mysql_data:/var/lib/mysql -d mysql:8.0
```

## Step 1: Navigate to the data_download folder
```bash
cd data_download
```

## Step 2: Install Python dependencies
```bash
pip install -r requirements.txt
```

## Step 3: Download 911 data from Boston API
```bash
python download_911_data.py
```

This will:
- Download all 911/crime data from Boston's open data portal
- Save it as a CSV file with timestamp
- Filter for shots fired incidents
- Show data statistics

## Step 4: Import data into MySQL
```bash
python import_911_to_mysql.py
```

This will:
- Connect to your MySQL database
- Create the required tables (shots_fired_data, homicide_data)
- Import the downloaded data
- Show import statistics

## Step 5: Verify the data
Connect to MySQL and check the data:
```bash
docker exec -it rethinkai-mysql mysql -u rethinkai_user -p
```

Enter password: `MySecureUserPass123!`

Then run these SQL queries:
```sql
USE rethinkai_db;

-- Check shots fired data
SELECT COUNT(*) as shots_fired_count FROM shots_fired_data;

-- Check homicide data  
SELECT COUNT(*) as homicide_count FROM homicide_data;

-- Sample data
SELECT * FROM shots_fired_data LIMIT 5;

-- Check date range
SELECT MIN(incident_date_time) as earliest, MAX(incident_date_time) as latest FROM shots_fired_data;
```

## Step 6: Test the API
Now you can test your API with the imported data:
```bash
cd ../api
python api.py
```

## Troubleshooting

### If download fails:
- Check your internet connection
- The Boston API might be temporarily down
- Try running the script again

### If import fails:
- Make sure MySQL container is running
- Check database credentials in the script
- Ensure the CSV file was created successfully

### If API doesn't work:
- Make sure your .env file has the correct database settings
- Check that the tables were created successfully
- Verify the data was imported correctly

## Expected Results

After running all commands, you should have:
- ✅ Downloaded CSV file with 911 data
- ✅ Created MySQL tables: shots_fired_data, homicide_data
- ✅ Imported thousands of records
- ✅ Working API that can query the data

## File Structure
```
data_download/
├── download_911_data.py      # Downloads data from Boston API
├── import_911_to_mysql.py    # Imports data to MySQL
├── requirements.txt          # Python dependencies
├── README.md                 # Documentation
├── COMMANDS.md              # This file
└── boston_911_data_*.csv    # Downloaded data (created after step 3)
```
