Param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$Args
)

python -m tinman.cli.main @Args