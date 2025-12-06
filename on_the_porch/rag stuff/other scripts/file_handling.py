import csv

def budget_to_text():
    """Convert budget CSV data into narrative text for vector DB."""
    
    # Read the CSV data
    with open('../../api/datastore/budget_filtered.txt', 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    
    # Convert each row to narrative text
    text_entries = []
    
    for row in rows:
        # Extract key fields
        dept = row.get('Department', 'Unknown Department')
        project = row.get('Project_Name', 'Unnamed Project')
        scope = row.get('Scope_Of_Work', 'No description available')
        neighborhood = row.get('Neighborhood', 'Unknown Location')
        status = row.get('Project_Status', 'Status unknown')
        total_budget = row.get('Total_Project_Budget', '0')
        
        # Create narrative text
        narrative = f"Project: {project}\n"
        narrative += f"Department: {dept}\n"
        narrative += f"Location: {neighborhood}\n"
        narrative += f"Status: {status}\n"
        narrative += f"Total Budget: ${total_budget}\n"
        narrative += f"Description: {scope}\n"
        narrative += "-" * 80 + "\n"
        
        text_entries.append(narrative)
    
    # Write to text file
    output_file = 'Data/boston_budget_projects.txt'
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(text_entries))
    
    print(f"Converted {len(text_entries)} projects to text format")
    print(f"Output saved to: {output_file}")

if __name__ == "__main__":
    budget_to_text()

