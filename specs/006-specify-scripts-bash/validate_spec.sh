#!/bin/bash

# Specification Validation Script
# For: Real-Time Whale Detection Dashboard

echo "=================================================="
echo "   SPECIFICATION QUALITY VALIDATION"
echo "=================================================="
echo ""
echo "Feature: Real-Time Whale Detection Dashboard"
echo "Branch: 006-specify-scripts-bash"
echo "Date: $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# Color codes for output
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color

# Counters
PASS=0
WARN=0
FAIL=0

# Function to check requirement
check_requirement() {
    local status=$1
    local description=$2

    case $status in
        "pass")
            echo -e "${GREEN}✅ PASS${NC}: $description"
            ((PASS++))
            ;;
        "warn")
            echo -e "${YELLOW}⚠️  WARN${NC}: $description"
            ((WARN++))
            ;;
        "fail")
            echo -e "${RED}❌ FAIL${NC}: $description"
            ((FAIL++))
            ;;
    esac
}

echo "──────────────────────────────────────────────────"
echo "1. CHECKING SPECIFICATION FILE"
echo "──────────────────────────────────────────────────"

if [ -f "spec.md" ]; then
    check_requirement "pass" "Specification file exists"

    # Check file size
    SIZE=$(stat -c%s "spec.md" 2>/dev/null || stat -f%z "spec.md" 2>/dev/null)
    if [ "$SIZE" -gt 1000 ]; then
        check_requirement "pass" "Specification has substantial content (${SIZE} bytes)"
    else
        check_requirement "fail" "Specification too small (${SIZE} bytes)"
    fi
else
    check_requirement "fail" "Specification file not found"
    exit 1
fi

echo ""
echo "──────────────────────────────────────────────────"
echo "2. CHECKING USER STORIES"
echo "──────────────────────────────────────────────────"

# Check for user stories
USER_STORIES=$(grep -c "User Story" spec.md)
if [ "$USER_STORIES" -ge 3 ]; then
    check_requirement "pass" "Found $USER_STORIES user stories (minimum: 3)"
else
    check_requirement "fail" "Only $USER_STORIES user stories found (minimum: 3)"
fi

# Check for priorities
if grep -q "Priority: P1" spec.md && grep -q "Priority: P2" spec.md; then
    check_requirement "pass" "User stories have priorities"
else
    check_requirement "warn" "Missing priority classifications"
fi

# Check for acceptance scenarios
SCENARIOS=$(grep -c "Given.*When.*Then" spec.md)
if [ "$SCENARIOS" -ge 5 ]; then
    check_requirement "pass" "Found $SCENARIOS acceptance scenarios"
else
    check_requirement "warn" "Only $SCENARIOS acceptance scenarios found"
fi

echo ""
echo "──────────────────────────────────────────────────"
echo "3. CHECKING FUNCTIONAL REQUIREMENTS"
echo "──────────────────────────────────────────────────"

# Count functional requirements
FR_COUNT=$(grep -c "FR-[0-9]" spec.md)
if [ "$FR_COUNT" -ge 10 ]; then
    check_requirement "pass" "Found $FR_COUNT functional requirements"
else
    check_requirement "warn" "Only $FR_COUNT functional requirements"
fi

# Check for RFC 2119 keywords
if grep -q "MUST\|SHOULD\|MAY" spec.md; then
    check_requirement "pass" "Uses RFC 2119 keywords"
else
    check_requirement "warn" "Missing RFC 2119 keywords (MUST/SHOULD/MAY)"
fi

# Check for clarifications needed
CLARIFICATIONS=$(grep -c "NEEDS CLARIFICATION" spec.md)
if [ "$CLARIFICATIONS" -eq 0 ]; then
    check_requirement "pass" "No clarifications needed"
else
    check_requirement "warn" "Found $CLARIFICATIONS items needing clarification"
fi

echo ""
echo "──────────────────────────────────────────────────"
echo "4. CHECKING SUCCESS CRITERIA"
echo "──────────────────────────────────────────────────"

# Count success criteria
SC_COUNT=$(grep -c "SC-[0-9]" spec.md)
if [ "$SC_COUNT" -ge 5 ]; then
    check_requirement "pass" "Found $SC_COUNT success criteria"
else
    check_requirement "warn" "Only $SC_COUNT success criteria"
fi

# Check for measurable metrics
if grep -q "seconds\|milliseconds\|%" spec.md; then
    check_requirement "pass" "Contains measurable metrics"
else
    check_requirement "warn" "Missing specific measurable metrics"
fi

echo ""
echo "──────────────────────────────────────────────────"
echo "5. CHECKING KEY ENTITIES"
echo "──────────────────────────────────────────────────"

# Check for entity definitions
if grep -q "Key Entities" spec.md; then
    check_requirement "pass" "Key entities section exists"

    # Check specific entities
    if grep -q "Whale Transaction" spec.md; then
        check_requirement "pass" "Whale Transaction entity defined"
    else
        check_requirement "fail" "Missing Whale Transaction entity"
    fi

    if grep -q "Net Flow" spec.md; then
        check_requirement "pass" "Net Flow concept defined"
    else
        check_requirement "warn" "Missing Net Flow definition"
    fi
else
    check_requirement "fail" "Missing Key Entities section"
fi

echo ""
echo "──────────────────────────────────────────────────"
echo "6. CHECKING EDGE CASES"
echo "──────────────────────────────────────────────────"

if grep -q "Edge Cases" spec.md; then
    check_requirement "pass" "Edge cases section exists"

    # Count edge cases
    EDGE_COUNT=$(grep -c "^- " spec.md | head -20 | tail -10)
    if [ "$EDGE_COUNT" -ge 3 ]; then
        check_requirement "pass" "Multiple edge cases identified"
    else
        check_requirement "warn" "Few edge cases identified"
    fi
else
    check_requirement "warn" "No explicit edge cases section"
fi

echo ""
echo "──────────────────────────────────────────────────"
echo "7. SPECIFIC REQUIREMENTS CHECK"
echo "──────────────────────────────────────────────────"

# Check for clarification items
echo ""
echo "Items requiring clarification:"
grep "NEEDS CLARIFICATION" spec.md | while read -r line; do
    echo "  ⚠️  $line"
done

echo ""
echo "=================================================="
echo "                VALIDATION SUMMARY"
echo "=================================================="
echo ""
echo -e "${GREEN}✅ Passed:${NC} $PASS"
echo -e "${YELLOW}⚠️  Warnings:${NC} $WARN"
echo -e "${RED}❌ Failed:${NC} $FAIL"
echo ""

# Calculate quality score
TOTAL=$((PASS + WARN + FAIL))
if [ "$TOTAL" -gt 0 ]; then
    QUALITY=$((PASS * 100 / TOTAL))
    echo "Quality Score: ${QUALITY}%"
    echo ""

    if [ "$FAIL" -eq 0 ] && [ "$WARN" -le 3 ]; then
        echo -e "${GREEN}✅ VALIDATION PASSED${NC}"
        echo "Specification is ready for planning phase"
        EXIT_CODE=0
    elif [ "$FAIL" -eq 0 ]; then
        echo -e "${YELLOW}⚠️  VALIDATION PASSED WITH WARNINGS${NC}"
        echo "Address warnings before proceeding to planning"
        EXIT_CODE=0
    else
        echo -e "${RED}❌ VALIDATION FAILED${NC}"
        echo "Critical issues must be fixed before proceeding"
        EXIT_CODE=1
    fi
else
    echo "Error: No checks performed"
    EXIT_CODE=2
fi

echo ""
echo "──────────────────────────────────────────────────"
echo "NEXT STEPS:"
echo "──────────────────────────────────────────────────"

if [ "$WARN" -gt 0 ]; then
    echo "1. Address the $WARN warnings identified above"
    echo "2. Get clarification on ambiguous requirements:"
    grep "NEEDS CLARIFICATION" spec.md | head -3
    echo "3. Re-run validation: ./validate_spec.sh"
    echo "4. Proceed to planning: /speckit.plan"
else
    echo "1. Review the specification one more time"
    echo "2. Proceed to planning phase: /speckit.plan"
fi

echo ""
exit $EXIT_CODE