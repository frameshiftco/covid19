import argparse
import csv
import psycopg2
import coronadb
from jhudata import OVERRIDES
from jhudata import OVERRIDE_COUNTIES_WITH_DATA

def review(source):
    with get_db_connection(coronadb.host, coronadb.port, coronadb.database, coronadb.user, coronadb.password) as db:
        all_counties = {}
        with db.cursor() as cursor:
            cursor.execute("select c.fips, c.state, c.county, c.county_num, j.cases, j.file_date from covid19.census c left outer join covid19.jhu_derived j on c.fips=j.fips and j.cases is not null and j.cases > 0 order by c.fips, j.file_date desc")
            rows = cursor.fetchall()

            last_fips = 'XXXXX'
            last_county = None
            has_nonzero_cases = False

            for result in rows:
                fips = result[0]
                cases = result[4]
                if fips == last_fips:
                    if cases is not None and cases > 0 and not has_nonzero_cases:
                        last_county["last_nonzero_date"] = result[5]
                        has_nonzero_cases = True

                else:
                    state = result[1]
                    county = result[2]
                    is_state = result[3] == 0

                    last_county = {"fips": fips, "state": state, "county": county, "is_state": is_state, "last_nonzero_date": None}
                    last_fips = fips
                    if cases is not None and cases > 0:
                        last_county["last_nonzero_date"] = result[5]
                        has_nonzero_cases = True
                    else:
                        has_nonzero_cases = False

                    all_counties[fips] = last_county

        print("Found " + str(len(all_counties)) + " counties")

        file = open(source, 'r', encoding="utf-8-sig")
        lines = file.readlines()

        header = lines[0].strip()
        lines.pop(0)
        if header == "FIPS,Admin2,Province_State,Country_Region,Last_Update,Lat,Long_,Confirmed,Deaths,Recovered,Active,Combined_Key":
            parse_counties(lines, all_counties, OVERRIDES, OVERRIDE_COUNTIES_WITH_DATA)

        else:
            raise ValueError("Unrecognized header format: " + header)


def parse_number(original):
    if original is None or original == '':
        return None

    try:
        return int(original)
    except ValueError:
        print("Silently converting \"" + original + "\" to None")
        return None


def parse_counties(lines, all_counties, overrides, overrides_without_data):
    count = 1
    counties_matched = 0

    found_counties = []

    used_overrides = []

    reader = csv.reader(lines, delimiter=',')
    for row in reader:
        fips = row[0]
        county = row[1]
        state = row[2]
        country = row[3]
        if country == 'US':
            if fips is None or fips == '':
                if state in overrides:
                    state_overrides = overrides[state]
                    if county in state_overrides:
                        override_result = state_overrides[county]
                        used_overrides.append(state + "." + county)
                        # print("No FIPS for " + county + " " + state + ", but override found to " + override_result)
                        fips = override_result
                    else:
                        print("No FIPS for " + county + " " + state)

                        fips = None
                else:
                    print("No FIPS for " + county + " " + state)
                    fips = None

            if fips is not None:
                if len(fips) == 4:
                    print("Fixing incorrect FIPS code")
                    fips = '0' + fips

                # last_update = row[4]
                # lat = row[5]
                # long = row[6]
                # cases = row[7]
                # deaths = row[8]
                # recovered = row[9]
                # active = row[10]
                # combined_key = row[11]

                if fips in all_counties:
                    county_details = all_counties[fips]
                    counties_matched += 1
                    found_counties.append(fips)
                else:
                    if fips not in ['XXXXX','88888','99999','66000']:
                        print("County details not found for FIPS=" + fips + ", " + state + " " + county)

    print("Counties Matched: " + str(counties_matched))

    # Now do the reverse comparison
    reverse_matched = 0
    unmatched_counties_without_data = 0
    for fips in all_counties:
        if fips in found_counties:
            reverse_matched += 1
        else:
            if fips in all_counties:
                county_details = all_counties[fips]
                if "last_nonzero_date" not in county_details or county_details["last_nonzero_date"] is None:
                    unmatched_counties_without_data += 1
                else:
                    state = county_details['state']
                    county = county_details['county']
                    last_nonzero = county_details['last_nonzero_date']
                    if fips not in overrides_without_data:
                        print("No data for county " + fips + " " + state + " " + county + ", last data was " + str(last_nonzero))
                    else:
                        overrides_without_data.remove(fips)

    print("Reverse matched: " + str(reverse_matched))

    if len(overrides_without_data) > 0:
        print("WARNING: Counties flagged to ignore no data, but data found")
        print(overrides_without_data)

    for state in overrides:
        state_overrides = overrides[state]
        for county in state_overrides:
            key = state + "." + county
            if key not in used_overrides:
                print("WARNING: Unused override: " + key)


def get_db_connection(host, port, name, user, pw):
    return psycopg2.connect(dbname=name, port=port, user=user, host=host, password=pw)


parser = argparse.ArgumentParser(description='Script to pre-process and report issues in JHU data before loading into the database')
parser.add_argument("--source", required=True, type=str, help="Directory or single file to load")

args = parser.parse_args()

review(args.source)