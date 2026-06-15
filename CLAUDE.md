# File Backup Utility

Python utility for backing compressing folders and moving folders, then restoring them from external harddrive. 

# Convensions

* No packages outside the standard library may be used
* Failure in copy and compression stage should cause the whole script to fail loudly
* Avoid compressed files over 1GB, descend file hierarchy until all files and directories at that level can be compressed under 1GB
* always checkout a new branch before making changes