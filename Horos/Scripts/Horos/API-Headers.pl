#!/usr/bin/perl

use strict;
use File::Copy qw(copy);
use File::Basename qw(basename);
my $destination = "$ENV{TARGET_BUILD_DIR}/$ENV{PUBLIC_HEADERS_FOLDER_PATH}";

mkdir $destination unless -d $destination;
open my $Horos_h, ">", "$destination/Horos.h" or die $!;

print {$Horos_h} "#ifndef __Horos_API\n#define __Horos_API\n\n";

my @fromdirs = ( "$ENV{PROJECT_DIR}/Nitrogen/Sources", "$ENV{PROJECT_DIR}/Nitrogen/Sources/JSON", "$ENV{PROJECT_DIR}/Horos/Sources" );
# Only DDKeychain is part of the public DICOM networking dependency graph;
# do not publish the HTTP server's other implementation headers.
my @fromfiles = ( "$ENV{PROJECT_DIR}/cocoahttpserver/DDKeychain.h" );

print STDERR "API-Headers.pl debug\n";
print STDERR "TARGET_BUILD_DIR=$ENV{TARGET_BUILD_DIR}\n";
print STDERR "PUBLIC_HEADERS_FOLDER_PATH=$ENV{PUBLIC_HEADERS_FOLDER_PATH}\n";
print STDERR "DESTINATION=$destination\n";
print STDERR "PROJECT_DIR=$ENV{PROJECT_DIR}\n";

foreach my $root (@fromdirs) {
    opendir(my $dir, $root) or die "Cannot open $root: $!";
    
    my @files = readdir($dir);
    foreach my $filename (@files) {
        next unless -f "$root/$filename" && $filename =~ /\.h$/s;

        if ($filename eq "Horos.h") {
            open my $base_header, "<", "$root/$filename" or die "Cannot open $root/$filename: $!";
            while (my $line = <$base_header>) {
                print {$Horos_h} $line;
            }
            close $base_header or die "Cannot close $root/$filename: $!";
            print {$Horos_h} "\n";
            next;
        }

        print STDERR "Copying $root/$filename -> $destination/".(basename $filename)."\n";
        my $target = "$destination/".(basename $filename);
        copy("$root/$filename", $target) or die "Copy failed: $root/$filename -> $target: $!";
        print {$Horos_h} "#include <Horos/$filename>\n";
    }
    
    closedir($dir) or die "Cannot close $root: $!";
}

foreach my $source (@fromfiles) {
    my $filename = basename $source;
    my $target = "$destination/$filename";
    copy($source, $target) or die "Copy failed: $source -> $target: $!";
    print {$Horos_h} "#include <Horos/$filename>\n";
}

print {$Horos_h} "\n#endif\n";
close $Horos_h or die "Cannot close $destination/Horos.h: $!";

chdir "$ENV{TARGET_BUILD_DIR}/$ENV{FULL_PRODUCT_NAME}";
symlink "Versions/Current/Headers", "Headers";

exit 0;
