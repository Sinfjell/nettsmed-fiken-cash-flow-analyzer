
I Fiken API er det endepunktet
👉 /companies/{companySlug}/transactions
du bruker for å hente bilagstransaksjoner — altså selve grunnlaget for en kontantstrømanalyse.

Se i swagger.yaml for detajlert info! 

APIet kan leses her https://api.fiken.no/api/v2/docs/#/transactions/getTransactions 

# Transactions
transactions


GET
/companies/{companySlug}/transactions


Returns all transactions for the specified company

Parameters
Try it out
Name	Description
page
integer
(query)
Returns the number of the page to return. Valid page values are integers from 0 to the total number of pages. Default value is 0.

Default value : 0

0
pageSize
integer
(query)
Defines the number of entries to return on each page. Maximum number of results that can be returned at one time are 100. Default value is 25.

Default value : 25

25
lastModified
string($date)
(query)
Filter based on date of last modification. Returns results that were last modified on the date provided as a parameter value. Dates are represented as strings formatted as YYYY-MM-DD. Example: January 1st, 1970: "1970-01-01"

lastModified
lastModifiedLe
string($date)
(query)
Returns results that have been last modified before or on the date provided as a parameter value. Dates are represented as strings formatted as YYYY-MM-DD. Example: January 1st, 1970: "1970-01-01"

lastModifiedLe
lastModifiedLt
string($date)
(query)
Returns results that have been last modified strictly before the date provided as a parameter value. Dates are represented as strings formatted as YYYY-MM-DD. Example: January 1st, 1970: "1970-01-01"

lastModifiedLt
lastModifiedGe
string($date)
(query)
Returns results that have been last modified after or on the date provided as a parameter value. Dates are represented as strings formatted as YYYY-MM-DD. Example: January 1st, 1970: "1970-01-01"

lastModifiedGe
lastModifiedGt
string($date)
(query)
Returns results that have been last modified strictly after the date provided as a parameter value. Dates are represented as strings formatted as YYYY-MM-DD. Example: January 1st, 1970: "1970-01-01"

lastModifiedGt
createdDate
string($date)
(query)
Dates are represented as strings formatted as YYYY-MM-DD. Example: January 1st, 1970: "1970-01-01"

createdDate
createdDateLe
string($date)
(query)
Returns results that were created before or on the date provided as a parameter value. Dates are represented as strings formatted as YYYY-MM-DD. Example: January 1st, 1970: "1970-01-01"

createdDateLe
createdDateLt
string($date)
(query)
Returns results that were created strictly before the date provided as a parameter value. Dates are represented as strings formatted as YYYY-MM-DD. Example: January 1st, 1970: "1970-01-01"

createdDateLt
createdDateGe
string($date)
(query)
Returns results that were created after or on the date provided as a parameter value. Dates are represented as strings formatted as YYYY-MM-DD. Example: January 1st, 1970: "1970-01-01"

createdDateGe
createdDateGt
string($date)
(query)
Returns results that were created strictly after the date provided as a parameter value. Dates are represented as strings formatted as YYYY-MM-DD. Example: January 1st, 1970: "1970-01-01"

createdDateGt
companySlug *
string
(path)
Slug of company to retrieve

companySlug
Responses
Code	Description	Links
200	
OK

Media type

application/json
Controls Accept header.
Example Value
Schema
[
  {
    "transactionId": 734083065,
    "createdDate": "2018-04-03",
    "lastModifiedDate": "2018-04-03",
    "description": "string",
    "type": "General Journal Entry",
    "entries": [
      {
        "journalEntryId": 0,
        "createdDate": "2018-04-03",
        "lastModifiedDate": "2018-04-03",
        "transactionId": 0,
        "offsetTransactionId": 0,
        "journalEntryNumber": 18,
        "description": "Purchase, Schweigaards Gate 34 AS (invoice nr 26083)",
        "date": "2018-04-03",
        "lines": [
          {
            "amount": 310000,
            "account": "2400:20079",
            "vatCode": "1",
            "projectId": [
              0
            ],
            "lastModifiedDate": "2018-04-03"
          }
        ],
        "attachments": [
          {
            "identifier": "24760",
            "downloadUrl": "string",
            "downloadUrlWithFikenNormalUserCredentials": "string",
            "comment": "string",
            "type": "invoice"
          }
        ]
      }
    ]
  }
]
Headers:
Name	Description	Type
Fiken-Api-Page	
From the request header

integer
Fiken-Api-Page-Size	
From the request header

integer
Fiken-Api-Page-Count	
The total number of pages in this resource with this page size

integer
Fiken-Api-Result-Count	
The total number of elements in this resource

integer 


# Pagination and filtering
Pagination, Sorting & Filtering
Pagination, sorting and filtering query parameters are all optional.

URI	Pagination?	Sortable?	Sortable Fields	Filterable?	Filtered Fields
https://api.fiken.no/api/v2/companies	Yes	Yes	createdDate, name, organizationNumber	No	
https://api.fiken.no/api/v2/companies/{companySlug}/accounts	No	No		Yes	fromAccount, toAccount
https://api.fiken.no/api/v2/companies/{companySlug}/accountBalances	Yes	No		Yes	fromAccount, toAccount
https://api.fiken.no/api/v2/companies/{companySlug}/bankAccounts	Yes	No		Yes	inactive
https://api.fiken.no/api/v2/companies/{companySlug}/bankBalances	Yes	No		Yes	date
https://api.fiken.no/api/v2/companies/{companySlug}/contacts	Yes	Yes	createdDate, lastModified	Yes	supplierNumber, customerNumber, memberNumber, memberNumberString, name, organizationNumber, email, group, lastModified, createdDate, inactive, phoneNumber
https://api.fiken.no/api/v2/companies/{companySlug}/creditNotes	Yes	No		Yes	issueDate, lastModified, settled, customerId
https://api.fiken.no/api/v2/companies/{companySlug}/inbox	Yes	Yes	createdDate, name	Yes	status, name
https://api.fiken.no/api/v2/companies/{companySlug}/invoices	Yes	No		Yes	issueDate, lastModified, dueDate, settled, customerId, orderReference, invoiceDraftUuid
https://api.fiken.no/api/v2/companies/{companySlug}/invoices/drafts	Yes	No		No	
https://api.fiken.no/api/v2/companies/{companySlug}/journalEntries	Yes	No		Yes	date
https://api.fiken.no/api/v2/companies/{companySlug}/offers	Yes	No		No	
https://api.fiken.no/api/v2/companies/{companySlug}/orderConfirmations	Yes	No		No	
https://api.fiken.no/api/v2/companies/{companySlug}/products	Yes	No		Yes	name, productNumber, active, createdDate, lastModified
https://api.fiken.no/api/v2/companies/{companySlug}/projects	Yes	No		Yes	completed
https://api.fiken.no/api/v2/companies/{companySlug}/purchases	Yes	Yes	createdDate	No	date
https://api.fiken.no/api/v2/companies/{companySlug}/purchases/drafts	Yes	No		No	
https://api.fiken.no/api/v2/companies/{companySlug}/sales	Yes	No		Yes	saleNumber, lastModified, date, contactId
https://api.fiken.no/api/v2/companies/{companySlug}/sales/drafts	Yes	No		No	
https://api.fiken.no/api/v2/companies/{companySlug}/transactions	Yes	No		Yes	createdDate, lastModified
Pagination
By default the API sets page=0 and pageSize=25 and returns the first 25 elements in a collection resource, if nothing else is specified. PageSize has a maximum value of 100 meaning that you can only access at most 100 elements at once.

To request a collection resource with pagination, query the resource with the query filters page and pageSize, note that both query parameters need to be set to enable pagination. The page counter starts at 0. The response will contain up to Fiken-Api-Page-Size elements and the response headers below, detailing how many elements the resource has in total and the total number of pages as well.

By default the API returns the resources in the order they were created, if nothing else is specified in the documentation.

Pagination Response Headers
Response Header	Format	Description
Fiken-Api-Page	integer	From the request header
Fiken-Api-Page-Size	integer	From the request header
Fiken-Api-Page-Count	integer	The total number of pages in this resource with this page size
Fiken-Api-Result-Count	integer	The total number of elements in this resource
Sorting
To change the sort order for a resource, set the sortBy query parameter to a sort field in either ascending or descending order. Ex: https://api.fiken.no/api/v2/companies?sortBy=name%20asc

Filtering
Some collections support filtering, and depending on the type of field, different filters can be used. Dates are the most complex, and allow you do apply different filters with different parameter names. For instance, for a field called date, the following mutations are available:

Parameter	Field	Format	Description
date	date	yyyy-MM-dd	date equal to parameter value
dateLe	date	yyyy-MM-dd	date less than or equal to parameter value
dateLt	date	yyyy-MM-dd	date less than parameter value
dateGe	date	yyyy-MM-dd	date greater than or equal to parameter value
dateGt	date	yyyy-MM-dd	date greater than parameter value
All date-fields will have these mutations of parameter name that applies

