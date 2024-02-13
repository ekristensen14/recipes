$csv = Import-Csv "/Users/erebacz/distro_csv.csv" -Delimiter ";"
$csv = $csv[0]

foreach($row in $csv){
    # Check if distro exists
    $assigned = Get-DistributionGroup -Identity $row.assigned
    if(!$assigned){
        "Assigned group ($($row.assigned)) does not exist, stopping"
        return
    }
    $dynamic = Get-DynamicDistributionGroup -Identity $row.dynamic
    if(!$dynamic){
        "Dynamic group ($($row.dynamic)) does not exist, stopping"
        return
    }
    "Adding '$($row.dynamic)' to '$($row.assigned)'"
    try {
        Add-DistributionGroupMember -Identity $row.assigned -Member $row.dynamic
        "Success"
    }
    catch {
        "Failure"
    }
}
