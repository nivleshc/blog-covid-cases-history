# blog-covid-cases-history
This repository contains code for deploying a solution in AWS, to create a Serverless website that displays a history for the NSW COVID-19 cases and vaccination details.

The solution uses AWS Serverless Application Model (SAM) to deploy resources in AWS. The AWS Lambda function is written in Python 3.7.

The website will be updated automatically, using data retrieved from the following external sources: 

[New South Wales Government Health](https://www.health.nsw.gov.au/Infectious/covid-19/Pages/stats-nsw.aspx)


## Preparation
Clone this repository using the following command.
```
git clone https://github.com/nivleshc/blog-covid-cases-history.git
```

Export the following environment variables.

```
export AWS_PROFILE_NAME={aws profile to use}

export AWS_S3_BUCKET_NAME={name of aws s3 bucket to store SAM artefacts in}

export AWS_S3_WEBSITE_BUCKET_NAME={name of AWS S3 bucket that will contain the generated html file. This bucket must be already setup as a static website host}

export SLACK_WEBHOOK_URL={slack webhook url to use for sending slack notifications}
```

## Commands

For help, run the following command:
```
make
```
To deploy the code in this repository to your AWS account, use the following steps:

```
make package
make deploy
```

If you make any changes to **template.yaml**, first validate the changes by using the following command (validation is not required if you change other files):
```
make validate
```

After validation is successful, use the following command to deploy the changes:
```
make update
```
