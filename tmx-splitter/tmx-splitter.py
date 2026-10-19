import xml.etree.ElementTree as ET
from datetime import datetime
import os
import glob
from tqdm import tqdm

def process_tmx_file(input_path, split_datetime, folder_path):
    """Process a single TMX file with progress tracking, outputting only entries after split date"""
    filename = os.path.basename(input_path)
    name_part = os.path.splitext(filename)[0]
    
    # Output file goes in same folder as input
    output_after = os.path.join(folder_path, f"{name_part}_after_{split_datetime.strftime('%Y%m%d')}.tmx")
    
    # Read the entire file to get the header
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = []
        header_lines = []
        in_header = True
        
        # Read until we find the start of the body or end of header
        for line in f:
            if in_header:
                header_lines.append(line)
                if '<body>' in line.lower():
                    in_header = False
            else:
                lines.append(line)
    
    # Join the header lines
    header_content = ''.join(header_lines)
    
    with open(output_after, 'w', encoding='utf-8') as f_after:
        
        # Write the complete header to the output file
        f_after.write(header_content)
        
        # Get approximate file size for progress bar
        file_size = os.path.getsize(input_path)
        
        # Create progress bar for this file
        with tqdm(total=file_size, unit='B', unit_scale=True, 
                 desc=f"Processing {filename}", leave=False) as pbar:
            
            context = ET.iterparse(input_path, events=('start', 'end'))
            
            for event, elem in context:
                if event == 'end' and elem.tag == 'tu':
                    # Check for date on the TU element first
                    tu_date_str = elem.get('creationdate', '')[:8] or elem.get('changedate', '')[:8]
                    latest_date = None
                    
                    if tu_date_str:
                        try:
                            latest_date = datetime.strptime(tu_date_str, "%Y%m%d")
                        except ValueError:
                            latest_date = None
                    
                    # If no date on TU, check all TUV elements
                    if latest_date is None:
                        for tuv in elem.findall('.//tuv'):
                            tuv_date_str = tuv.get('creationdate', '')[:8] or tuv.get('changedate', '')[:8]
                            if tuv_date_str:
                                try:
                                    tuv_date = datetime.strptime(tuv_date_str, "%Y%m%d")
                                    if latest_date is None or tuv_date > latest_date:
                                        latest_date = tuv_date
                                except ValueError:
                                    pass
                    
                    tu_xml = ET.tostring(elem, encoding='utf-8').decode('utf-8')
                    
                    # Keep the TU if it has a date >= split date
                    if latest_date and latest_date >= split_datetime:
                        f_after.write(tu_xml)
                    
                    # Update progress based on file position
                    pbar.update(f_after.tell() - pbar.n)
                    
                    elem.clear()
            
            # Write the closing tags
            f_after.write('</body>\n</tmx>\n')

def main():
    print("\nTMX File Splitter by Date")
    print("-------------------------")
    print("This tool will create new TMX files containing only entries")
    print("from the specified date onward.\n")
    
    # Get folder path
    folder_path = input("Enter the folder path containing TMX files: ").strip()
    while not os.path.isdir(folder_path):
        print("Error: Folder not found.")
        folder_path = input("Please enter a valid folder path: ").strip()
    
    # Get split date
    while True:
        date_input = input("Enter split date (YYYY/MM/DD format - only entries from this date onward will be kept): ").strip()
        try:
            split_datetime = datetime.strptime(date_input, "%Y/%m/%d")
            break
        except ValueError:
            print("Invalid date format. Please use YYYY/MM/DD format.")
    
    # Find TMX files
    tmx_files = glob.glob(os.path.join(folder_path, "*.tmx"))
    if not tmx_files:
        print("No TMX files found in the specified folder.")
        return
    
    print(f"\nFound {len(tmx_files)} TMX file(s) to process")
    
    # Main progress bar
    with tqdm(tmx_files, desc="Overall Progress", unit="file") as main_pbar:
        for tmx_file in main_pbar:
            main_pbar.set_postfix(file=os.path.basename(tmx_file)[:20])
            try:
                process_tmx_file(tmx_file, split_datetime, folder_path)
            except Exception as e:
                tqdm.write(f"Error processing {os.path.basename(tmx_file)}: {str(e)}")
    
    print("\nProcessing complete!")
    print(f"Created {len(tmx_files)} output file(s) in: {folder_path}")
    input("Press any key to exit...")

if __name__ == "__main__":
    main()
