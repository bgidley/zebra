VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "DocScan"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
Attribute VB_Ext_KEY = "SavedWithClassBuilder6" ,"Yes"
Attribute VB_Ext_KEY = "Top_Level" ,"Yes"
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
'/ produces a little documentation that covers the following
'/ 1. A list of Screen Names for each flow
'/ 2. A depenedency list for SubFlows
'/ 3. Indicate SubFlow steps with no SubFlow named

Option Explicit

Private mcolWorkflows As Collection
Private moAppSettings As Properties
Private Const mcstrModule = "DocScan"

'/ start the scan
Public Sub StartScan(Path As String, AppSettings As Properties)
    Const cstrFunc = "StartScan"
    On Error GoTo Err_Handler:
    Dim oScanPath As ScanPath
    Dim strFile As String
    Set mcolWorkflows = New Collection
    Set moAppSettings = AppSettings
    '/ build up a file list
    
    Set oScanPath = New ScanPath
    oScanPath.StartScan Path, ".acgwfd"
    
    '/ import the flows
    Do Until oScanPath.FileList.Count = 0
        strFile = oScanPath.FileList(1)
        ImportFlow strFile
        oScanPath.FileList.Remove 1
    Loop
    
    '/ now have a list of workflows, so can start the mapping process
    SaveToFile ValidatePath(Path) & "Workflow Screen Report.html", "<html>" & GetScreenNames(Path) & "</html>"
    SaveToFile ValidatePath(Path) & "Workflow SubFlow Dependency Report.html", "<html>" & GetFlowDeps & "</html>"
    Exit Sub
Err_Handler:
    Select Case StdErrMsg(Err, mcstrModule, cstrFunc & " parsing file " & strFile)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select

End Sub

Private Function GetFlowDeps() As String
    Dim strRtn As String
    Dim strHead As String
    Dim strErr As String
    Dim oFlow As Flow
    Dim oTaskDef As FlowNode
    Dim colUses As Collection
    Dim colUsedBy As Collection
    Dim colTemp As Collection
    
    '/ build up the keys in the dependency list
    Set colUses = New Collection
    Set colUsedBy = New Collection
    
    For Each oFlow In mcolWorkflows
        colUsedBy.Add New Collection, "@" & oFlow.Name
    Next
    
    For Each oFlow In mcolWorkflows
        Set colTemp = New Collection
        colUses.Add colTemp, "@" & oFlow.Name
        
        For Each oTaskDef In oFlow.FlowSteps
            If oTaskDef.StepType = stSubFlow Then
                If FlowExists(oTaskDef.TypeProps("Flow Name").Value) Then
                    Set colTemp = colUses("@" & oFlow.Name)
                    colTemp.Add oTaskDef.TypeProps("Flow Name").Value
                    Set colTemp = colUsedBy("@" & oTaskDef.TypeProps("Flow Name").Value)
                    colTemp.Add oFlow.Name
                Else
                    strErr = strErr & "<tr>"
                    strErr = strErr & "<td>"
                    strErr = strErr & oFlow.Name
                    strErr = strErr & "</td>"
                    strErr = strErr & "<td>"
                    strErr = strErr & oTaskDef.TypeProps("ID").Value
                    strErr = strErr & "</td>"
                    strErr = strErr & "<td>"
                    strErr = strErr & oTaskDef.Caption
                    strErr = strErr & "</td>"
                    strErr = strErr & "<td>"
                    strErr = strErr & "The """ & oTaskDef.TypeProps("Flow Name").Value & """ flow specified by this step does not exist"
                    strErr = strErr & "</td>"
                    strErr = strErr & "</tr>"
                End If
            End If
        Next
    Next

    For Each oFlow In mcolWorkflows
        strRtn = strRtn & "<tr>"
        strRtn = strRtn & "<td>"
        strRtn = strRtn & oFlow.Name
        strRtn = strRtn & "</td>"
        strRtn = strRtn & "<td>"
        Set colTemp = colUses("@" & oFlow.Name)
        If colTemp.Count > 0 Then
            strRtn = strRtn & "<table>"
            Do Until colTemp.Count = 0
                strRtn = strRtn & "<tr>"
                strRtn = strRtn & "<td>"
                strRtn = strRtn & colTemp(1)
                strRtn = strRtn & "</td>"
                strRtn = strRtn & "</tr>"
                colTemp.Remove 1
            Loop
            strRtn = strRtn & "</table>"
        Else
            strRtn = strRtn & "[None]"
        End If
        strRtn = strRtn & "</td>"
        
        strRtn = strRtn & "<td>"
        Set colTemp = colUsedBy("@" & oFlow.Name)
        If colTemp.Count > 0 Then
            strRtn = strRtn & "<table>"
            Do Until colTemp.Count = 0
                strRtn = strRtn & "<tr>"
                strRtn = strRtn & "<td>"
                strRtn = strRtn & colTemp(1)
                strRtn = strRtn & "</td>"
                strRtn = strRtn & "</tr>"
                colTemp.Remove 1
            Loop
            strRtn = strRtn & "</table>"
        Else
            strRtn = strRtn & "[None]"
        End If
        strRtn = strRtn & "</td>"
        
        strRtn = strRtn & "</tr>"
    Next
    If Len(strRtn) > 0 Then
        strHead = strHead & "<H1>"
        strHead = strHead & "Flow Dependency Listing"
        strHead = strHead & "</H1>"
        strHead = strHead & "<p>"
        strHead = strHead & "Generated " & Now
        strHead = strHead & "</p>"
        strHead = strHead & "<table>"
        strHead = strHead & "<tr>"
        strHead = strHead & "<th>"
        strHead = strHead & "Flow Name"
        strHead = strHead & "</th>"
        strHead = strHead & "<th>"
        strHead = strHead & "Uses"
        strHead = strHead & "</th>"
        strHead = strHead & "<th>"
        strHead = strHead & "Used By"
        strHead = strHead & "</th>"
        strHead = strHead & "</tr>"
        strRtn = strHead & strRtn & "</table>"
    End If
    If Len(strErr) > 0 Then
        strHead = "<H1>"
        strHead = strHead & "Errors"
        strHead = strHead & "</H1>"
        strHead = strHead & "<table>"
        strHead = strHead & "<tr>"
        strHead = strHead & "<th>"
        strHead = strHead & "Flow Name"
        strHead = strHead & "</th>"
        strHead = strHead & "<th>"
        strHead = strHead & "Step ID"
        strHead = strHead & "</th>"
        strHead = strHead & "<th>"
        strHead = strHead & "Step Caption"
        strHead = strHead & "</th>"
        strHead = strHead & "<th>"
        strHead = strHead & "Issue"
        strHead = strHead & "</th>"
        strHead = strHead & "</tr>"
        strErr = strHead & strErr & "</table>"
    End If
    GetFlowDeps = strRtn & strErr
End Function

Private Function FlowExists(FlowName As String) As Boolean
    On Error GoTo Err_Handler
    Dim oTest As Flow
    Set oTest = mcolWorkflows("@" & FlowName)
    FlowExists = True
    Exit Function
Err_Handler:
    FlowExists = False
End Function


Private Sub SaveToFile(FileName As String, Content As String)
    Dim fh As Integer
    If Len(Dir$(FileName)) > 0 Then
        Kill FileName
    End If
    fh = FreeFile
    Open FileName For Output As fh
    Print #fh, Content
    Close #fh
End Sub

'/ returns a list of all screen names found in the workflows
Private Function GetScreenNames(FlowPath As String) As String
    Dim oFlow As Flow
    Dim oTaskDef As FlowNode
    Dim strRtn As String
    Dim strHead As String
    Dim strScreenPath As String
    Dim strCheckPath As String
    Dim strScreenName As String
    Dim lngTemp As Long
    
    
    '/ work out the path to screens
    strScreenPath = ValidatePath(FlowPath) & "..\..\webapp\templates\app\screens\"
    
    For Each oFlow In mcolWorkflows
        For Each oTaskDef In oFlow.FlowSteps
            If oTaskDef.TypeProps.Exists("Screen Name") Then
                strScreenName = oTaskDef.TypeProps.Item("Screen Name").Value
                strRtn = strRtn & "<tr>"
                strRtn = strRtn & "<td>"
                strRtn = strRtn & oFlow.Name
                strRtn = strRtn & "</td>"
                strRtn = strRtn & "<td>"
                strRtn = strRtn & oTaskDef.TypeProps.Item("ID").Value
                strRtn = strRtn & "</td>"
                strRtn = strRtn & "<td>"
                strRtn = strRtn & oTaskDef.Caption
                strRtn = strRtn & "</td>"
                strRtn = strRtn & "<td>"
                strRtn = strRtn & strScreenName
                strRtn = strRtn & "</td>"
                strRtn = strRtn & "<td>"
                    
                If Len(strScreenName) > 0 Then
                    lngTemp = InStrRev(strScreenName, ",")
                    If lngTemp > 0 Then
                        strCheckPath = Left$(strScreenName, lngTemp - 1)
                        strCheckPath = strCheckPath & "\" & Right$(strScreenName, Len(strScreenName) - lngTemp)
                    Else
                        strCheckPath = strScreenName
                    End If
                    strCheckPath = strScreenPath & strCheckPath
                    If Len(Dir$(strCheckPath)) > 0 Then
                        strRtn = strRtn & "Exists"
                    Else
                        strRtn = strRtn & "Missing"
                    End If
                Else
                    strRtn = strRtn & "One Click Action"
                End If
                strRtn = strRtn & "</td>"
                strRtn = strRtn & "</tr>"
                    
                
            End If
        Next
    Next
    If Len(strRtn) > 0 Then
        strHead = strHead & "<H1>"
        strHead = strHead & "Screen Listing"
        strHead = strHead & "</H1>"
        strHead = strHead & "<p>"
        strHead = strHead & "Generated " & Now
        strHead = strHead & "</p>"
        strHead = strHead & "<table>"
        strHead = strHead & "<tr>"
        strHead = strHead & "<th>"
        strHead = strHead & "Flow Name"
        strHead = strHead & "</th>"
        strHead = strHead & "<th>"
        strHead = strHead & "Step ID"
        strHead = strHead & "</th>"
        strHead = strHead & "<th>"
        strHead = strHead & "Step Caption"
        strHead = strHead & "</th>"
        strHead = strHead & "<th>"
        strHead = strHead & "Screen Name"
        strHead = strHead & "</th>"
        strHead = strHead & "<th>"
        strHead = strHead & "Status"
        strHead = strHead & "</th>"
        strHead = strHead & "</tr>"
        strRtn = strHead & strRtn & "</table>"
    End If
    GetScreenNames = strRtn
End Function

Private Sub ImportFlow(FileName As String)
    '# ZEBRA
    '# TODO
'    Dim oImport As FilterNative
'    Dim oFlow As Flow
'    Set oFlow = New Flow
'    Set oFlow.AppSettings = moAppSettings
'    Set oImport = New FilterNative
'
'    If Not oImport.Import(oFlow, FileName) Then
'        Debug.Print "Failed to import " & FileName
'    Else
'        mcolWorkflows.Add oFlow, "@" & UCase$(oFlow.Name)
'    End If
End Sub
