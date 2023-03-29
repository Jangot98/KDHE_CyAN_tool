# -*- coding: utf-8 -*-
"""
Created on Tue Sep 20 18:33:41 2022

CYANDataProcesssing_GEOG728Capstone.py

This script will take Kansas Department of Health and Environment in-situ data and find satellite derived cyanobacteria concentrations for the
 same day and location and output a table with the two side by side. The script will perform an analysis for the coordinate point as well
 as a 500m buffered region around the point.

Needs Spatial Analyst & Image Analyst

@author: angot
"""

___Author___ = "Jordan Angot"
___Version___ = "1.0"
___Email___ = "angot@ksu.edu"
___Status___ = "Prototype"

# Import libraries
import pandas as pd
import requests
from pathlib import Path
import arcpy
import os
from sys import exit


###########################################################
#### Importing Excel Sheets and Extracting Data ###########
###########################################################

# Please input the file path of the project folder
filePath = input("Please input the file path of the project folder: ")

# Program reads waterbody data from the "MarionRes" sheet
csv = input("Please input the fiel path of the CSV file from KDHE: ")

df = pd.read_csv(csv)

#######################################################
#### CREATE NEW COLUMN AND NAME IT "CYAN Data Tag"#####
#######################################################

df["Sample Date"] = pd.to_datetime(df["Sample Date"])
df["CYAN Data Tag"] = df["Sample Date"].dt.year.astype(str) + df["Sample Date"].dt.dayofyear.astype(str)

# Program pulls column names
dfColumns = df.columns

# If the column with the total algal cell count contains a 1 or 0 the program removes the row
df.drop(df.loc[df[dfColumns[3]]==0].index, inplace = True)
df.drop(df.loc[df[dfColumns[3]]==1].index, inplace = True)

# Gets unique Cyan Data Tags
Tags = df["CYAN Data Tag"].unique()
UniqueTags = Tags

###########################################################
#### Downloading the Data from the CYAN Portal ############
###########################################################


# Program reads entire text file and saves it as a string
file = open(filePath + "/CYAN.txt", "r")
TotalURLs = file.read()

# Program splits string into list
CYANLinks = TotalURLs.split()

# Converts array of unique tags to list
UniqueTagsList = UniqueTags.tolist()

# Generate appkey **********(<-This has an expiration date)**************
appkey = "?appkey=c5d75c38119bb68443fd106b2fe7ba4a412896bb"

# Set count variable
count = 1

# Set variable for the path which the tiff files will be saved to
CYANTiffFolderPath = filePath + "/CYANTiffDownloads/"

# Check if the folder path is empty and if not stop the script and return an error.
dir = os.listdir(CYANTiffFolderPath)
if len(dir) == 0:
    print("The folder for the CYAN tiff files is empty. The download can begin.")
else:
    exit("Please delete all files in the folder before running the tool.")



# Program loops through CYAN urls and the unique tags from the KDHE data and downloads the ones that match
print("The download is beginning.")
for w in range(len(CYANLinks)):
    for i in range(len(UniqueTagsList)):
        if str(UniqueTagsList[i]) in CYANLinks[w]:

            # This calls the url link with the appkey received from the oceandata website.
            response = requests.get(CYANLinks[w]+appkey)
            content = response.content

            # This pulls the file's identifying name containing the year and day of year from the url path name.
            file_name = CYANTiffFolderPath + CYANLinks[w].split('/')[-1]
            data_path = Path(file_name)
            data_path.write_bytes(content)
            print("{0} file(s) have been downloaded".format(count))
            count = count + 1
print("The downloads are complete.")


###########################################################
##### Add downloaded rasters to the geodatabase ###########
###########################################################

# Set path to workspace
gdb = input("Please input the file path of the ArcGIS project workspace: ")

# Set a second count variable
count2 = 1

# For each tiff file saved to the folder add it to the workspace and return a message.
for filename in os.listdir(CYANTiffFolderPath):
    if filename.endswith(".tif"):
        raster = CYANTiffFolderPath + filename
        arcpy.conversion.RasterToGeodatabase(raster, gdb)
        print("{0} raster(s) were added to the geodatabase.".format(count2))
        count2 = count2 + 1
    else:
        continue

###########################################################
#### Start Geoprocessing ##################################
###########################################################

# Allows for file overwrites
arcpy.env.overwriteOutput = True

# Set current workspace
currentWorkspace = gdb
arcpy.env.workspace = currentWorkspace


# Call the file path of the first tiff folder in the CYANTiffFolderPath
templatePath = CYANTiffFolderPath + os.listdir(CYANTiffFolderPath)[0]



# Convert Coordinate CSV files to points
desc = arcpy.Describe(templatePath)
sr = desc.spatialReference

x = df['x']
y = df['y']
SiteLabel = df["Site Label"]

L = []
for x,y,SiteLabel in zip(x,y,SiteLabel):
    if (x,y) not in L and (y,x) not in L and SiteLabel != "XA":
        L.append((x,y,SiteLabel))

L = pd.DataFrame(L)
L.rename(columns={0:"x"}, inplace=True)
L.rename(columns={1:"y"}, inplace=True)
L.rename(columns={2:"Site Label"}, inplace=True)

L.to_csv(filePath + "/TestLocations.csv")
arcpy.defense.CoordinateTableToPoint(filePath + "/TestLocations.csv", "TestingLocations", "x","DD_2","y", "WGS_1984_Web_Mercator_Auxiliary_Sphere")



# Create the the buffer around the testing locations
arcpy.analysis.Buffer("TestingLocations", "TestLocationsBuffered_500m", "1500 Meters")

# Values for NoValue(244) and Land(255) in the rasters are set to Null
rasterDataset = arcpy.ListRasters()
rasterList = rasterDataset

# Set a third count variable
count3 = 1

# For each raster added to the geodatabase perform some geoprocessing.
for raster2 in rasterList:

    # Set all raster values greater or equal to 254 to NULL
    outSetNull = arcpy.sa.SetNull(raster2, raster2, "VALUE >= 254")

    # Set a name for output raster after NULLS are set
    tag = raster2[1:8]
    name = "Date" + tag
    outSetNull.save(name)

    # Set local variables describing the variable paths
    rasPath = currentWorkspace + '\\' + name
    rasterCalc = currentWorkspace + "\\CellCount_" + name
    buffstatPath = currentWorkspace + "\BufferedZonalSt_" + name
    statPath = currentWorkspace + "\ZonalSt_" + name

    ###Buffered Location Analysis

    # Set expression that converts the cyanobacteria index number to the cell concetration in cells/mL
    expression = "int(6279.6*2.7182818284590**(0.0277*Value))"

    # Compute the expression for every raster and save it the the prefix CellCount_
    test = arcpy.ia.RasterCalculator([rasPath], ["Value"], expression)

    test.save(rasterCalc)

    # Compute the zonal statistics of the output raster from the above expression and save it to the buffered zonal statistics variable path
    arcpy.sa.ZonalStatisticsAsTable("TestLocationsBuffered_500m", "Site Label", rasterCalc, buffstatPath, "DATA", "ALL", "CURRENT_SLICE", 90, "AUTO_DETECT", "ARITHMETIC", 360)

    # Add a field to each output zonal statistics table for the CYAN date tag and compute it.
    arcpy.management.AddField(buffstatPath, "CYANTag", "TEXT")
    arcpy.management.CalculateField(buffstatPath, "CYANTag", tag)

    # Add a field for the KDHE cell count data that will be added later
    arcpy.management.AddField(buffstatPath, "KDHE_CC", "LONG")


    ### Point Location Analysis

    # Compute the zonal statistics of the output raster from the above expression and save it to the zonal statistics variable path
    arcpy.sa.ZonalStatisticsAsTable("TestingLocations", "Site Label", rasterCalc, statPath, "DATA", "ALL", "CURRENT_SLICE", 90, "AUTO_DETECT", "ARITHMETIC", 360)

    # Add a field to each output zonal statistics table for the CYAN date tag and compute it.
    arcpy.management.AddField(statPath, "CYANTag", "TEXT")
    arcpy.management.CalculateField(statPath, "CYANTag", tag)

    # Add a field for the CYAN cell count data and compute it. Since there is only one value in the "zone" the min can be used for computation.
    arcpy.management.AddField(statPath, "CC", "LONG")
    arcpy.management.CalculateField(statPath, "CC", "!MIN!", "PYTHON3", '', "LONG", "NO_ENFORCE_DOMAINS")

    # Add a field for the KDHE cell count data that will be added later
    arcpy.management.AddField(statPath, "KDHE_CC", "LONG")

    # Print a message each time a rater is processed.
    print("{0} Raster(s) processed".format(count3))
    count3 = count3 + 1


# Create a list of all the buffered zonal statistics tables and append them all together and save them to an output CSV file
tablesList = arcpy.ListTables("Buff*")
arcpy.management.Append(tablesList[1:],tablesList[0])
arcpy.conversion.TableToTable(tablesList[0], filePath + "/", "BufferedOutputTable.csv")

# Create a list of all the zonal statistics tables from the single point analsysis and append them all together and save them to an output CSV file
tablesList = arcpy.ListTables("Zonal*")
arcpy.management.Append(tablesList[1:],tablesList[0])
arcpy.conversion.TableToTable(tablesList[0], filePath + "/", "OutputTable.csv")

# Create a dataframe of the output buffered table
df3 = pd.read_csv(filePath + "\BufferedOutputTable.csv")

# Since 6280 cells/mL or less is actually below detection for the satellite these values are replaced by 0
df3["MIN"] = df3["MIN"].replace({6279.0: 0})
df3["MAX"] = df3["MAX"].replace({6279.0: 0})
df3["MEAN"] = df3["MEAN"].replace({6279.0: 0})

# When dropping the null values above makes the indexing not continuous the index is reset
df = df.reset_index(drop=True)

df['CYAN Data Tag'] = pd.to_numeric(df['CYAN Data Tag'])

# For each row in the output data frame if the CYAN date tag matches the date tag from the input KDHE data then the Cyanobacteria cell count is calculated and then added to the row
for row in range(len(df3)):
    for rows in range(len(df)):
        if df.loc[rows, "Site Label"] == df3.loc[row,"Site_Label"] and df.loc[rows, "CYAN Data Tag"] == df3.loc[row,"CYANTag"]:
            CellCount = df.loc[rows, "Total Algal Cell Count (cell/ml)"] * df.loc[rows,"Percent BlueGreen"]/100
            df3.loc[row,"KDHE_CC"] = CellCount
        else:
            continue

# Some of the values may match but either KDHE or the satellite product return no value. If this happens the row is dropped and resaved.
df3 = df3.dropna()
df3.to_csv(filePath + "\BufferedOutputTable.csv", index =False)

# Create a dataframe of the output table
df4 = pd.read_csv(filePath + "\OutputTable.csv")

# Since 6280 cells/mL or less is actually below detection for the satellite these values are replaced by 0
df4["CC"] = df4["CC"].replace({6279: 0})


# For each row in the output data frame if the CYAN date tag matches the date tag from the input KDHE data then the Cyanobacteria cell count is calculated and then added to the row
for row in range(len(df4)):
    for rows in range(len(df)):
        if df.loc[rows, "Site Label"] == df4.loc[row,"Site_Label"] and df.loc[rows, "CYAN Data Tag"] == df4.loc[row,"CYANTag"]:
            CellCount = df.loc[rows, "Total Algal Cell Count (cell/ml)"] * df.loc[rows,"Percent BlueGreen"]/100
            df4.loc[row,"KDHE_CC"] = CellCount
        else:
            continue

# Some of the values may match but either KDHE or the satellite product return no value. If this happens the row is dropped and resaved.
df4 = df4.dropna()
df4.to_csv(filePath + "\OutputTable.csv", index =False)
