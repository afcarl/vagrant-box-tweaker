#!/bin/bash

################################################################################
# Copyright (c) 2015 Genome Research Ltd.
#
# Author: Matthew Rahtz <matthew.rahtz@sanger.ac.uk>
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
################################################################################

# Provision using CFEngine 3.6

readonly POLICY_SERVER=cfengine.internal.foocorp.com
readonly DEFINE_CLASSES=internal

set -o errexit

if ! which cf-agent > /dev/null; then
    wget -q http://cfengine.package-repos.s3.amazonaws.com/community_binaries/cfengine-community_3.6.2-1_amd64.deb
    dpkg -i cfengine-community_3.6.2-1_amd64.deb
    /var/cfengine/bin/cf-agent --bootstrap "$POLICY_SERVER"
fi

echo "Updating promises..."
cf-agent -K -f update.cf

echo "Running cf-agent..."
converged=false
iteration_n=1
max_iterations=5
while ! $converged && (( iteration_n <= max_iterations )); do
    echo "Iteration $((iteration_n++))..."
    cf-agent -K -D "$DEFINE_CLASSES" -v > log
    outcome3=$outcome2
    outcome2=$outcome1
    # second grep extracts part which does NOT contain timestamp
    outcome1=$(grep -A1 Outcome log | grep -o 'verbose:.*')
    echo "$outcome1"
    if [[ $outcome1 == $outcome2 && $outcome2 == $outcome3 ]]; then
        converged=true
    fi
done

if $converged; then
    echo "Machine state appears to have converged"
else
    echo "Error: state not converged after $max_iterations iterations" >&2
    exit 1
fi
