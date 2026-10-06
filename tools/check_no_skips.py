"""Required release checks may not silently skip the independent SDK coverage."""
import sys
import xml.etree.ElementTree as ET
root=ET.parse(sys.argv[1]).getroot()
skipped=root.findall('.//testcase/skipped')
if skipped:
    raise SystemExit(f'Required release tests skipped: {len(skipped)}')
print('Required test report contains no skipped test cases.')
