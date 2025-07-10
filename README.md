SendDICOM is a Python class for automating the upload of DICOM files and associated radiomics CSV data to an XNAT server.

How it works when you run this pipeline:

-It updates the DICOM files, by writing a “treatment site” (like LUNG or KIDNEY) into the DICOM tag called BodyPartExamined.
This is only used because of the test data.

-This treatment site tells the system which XNAT project the data belongs to.

-It zips up the DICOMs and prepares them for upload.

-It figures out how to sort the data in XNAT with: The project name comes from the treatment site you added earlier, 
the patient’s name in the DICOM becomes the subject in XNAT and the patient ID becomes the session under that subject.
This means if you upload data with the same patient name and ID multiple times, XNAT merges them into the same session. Be careful with duplicate names and IDs to avoid overwriting data!

-Once the DICOM session is safely stored in XNAT, it uploads the CSV file into that same session as a resource.

Important Things to Know
Check your XNAT URL!
By default, this pipeline uses: http://digione-infrastructure-xnat-nginx-1:80
If your XNAT server lives somewhere else, you must change this, or your uploads will fail.

Running the Pipeline
The class can run on its own or as part of a RabbitMQ message consumer. For standalone use, the commented part below: if __name__ == "__main__"
and do not use the other part of __name__ == "__main__"