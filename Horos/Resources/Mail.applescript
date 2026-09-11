-- Mail.applescript
-- iPhoto

-- Copyright (c) 2003-2006 Apple Computer. All rights reserved.

on mail_images(email_subject, default_address, image_count, new_files, new_captions, new_comments, cancel_string)
	
	try
		-- Horos asks for Mail Automation consent before this handler runs.
		-- A bounded timeout avoids a silent hang if Mail never replies.
		with timeout of 90 seconds
		tell application "Mail"
			activate -- activate before creating message, or message will go behind main window if mail wasn't previously running [4370868]
			make new outgoing message with properties {subject:email_subject, visible:true}
			tell the result
				--				make new paragraph at beginning with data return
				try
					-- We have been having problems with inserting images before the signature.  There seems to
					-- be some sort of bug with attachments.  Even iterating the images backwards and inserting
					-- the images at the "beginning" doesn't work for more than 1 images.  Strange.
					-- Anyway, we note the signature here, remove the signature from the message, and then
					-- set the message signature back at the bottom.
					-- Peter
					set sig to the message signature
					name of sig -- if there is no signature, then this line fails, allowing us to detect that there was no signature
					set useSig to true
				on error
					set useSig to false
				end try
				repeat with image_idx from 1 to image_count
					make new attachment at end with properties {file name:item image_idx of new_files}
					
					set combined_caption to ""
					
					set this_caption to item image_idx of new_captions
					set this_comment to item image_idx of new_comments
					
					if (this_caption is not "") then
						set combined_caption to (combined_caption & this_caption & return)
					end if
					if (this_comment is not "") then
						set combined_caption to (combined_caption & this_comment & return)
					end if
					set combined_caption to (return & combined_caption & return)
					make new paragraph at end with data combined_caption
				end repeat
				if image_count is 0 then
					make new paragraph at beginning with data new_captions
				end if
				if useSig is true then
					set message signature to sig
				end if
			end tell
		end tell
		end timeout
		
	on error error_message number error_number
		-- Report failures to Horos; asking Finder to display them requires another permission.
		error error_message number error_number
	end try
	return 0
end mail_images
