VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "Tasks"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = True
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
Option Explicit
Private mParentContainer As Container
Private mCol As Collection
Private WithEvents mContainer As Container
Attribute mContainer.VB_VarHelpID = -1
Friend Property Set ParentContainer(v As Container)
    Set mParentContainer = v
End Property

Public Property Get ProcessDef() As ProcessDef
    Set ProcessDef = mParentContainer.GetParent
End Property

Private Sub Class_Initialize()
    Set mCol = New Collection
    Set mContainer = New ACGContainer.Container
End Sub

Public Function Add(Optional GUID As String = vbNullString) As TaskDef
    Dim oNew As TaskDef
    Set oNew = New TaskDef
    Set oNew.ParentContainer = mContainer
    
    If Len(GUID) = 0 Then
        oNew.GUID = CreateGUID
    Else
        oNew.GUID = GUID
    End If
    
    mCol.Add oNew, oNew.GUID
    
    Set Add = oNew
    
End Function

Public Property Get Item(vntIndexKey As Variant) As TaskDef
Attribute Item.VB_UserMemId = 0
    Set Item = mCol(vntIndexKey)
End Property

Public Property Get Count() As Long
    Count = mCol.Count
End Property

Public Sub Remove(vntIndexKey As Variant)
    Dim oRemove As TaskDef
    Set oRemove = mCol(vntIndexKey)
    mCol.Remove vntIndexKey
    '# now remove routings
    Dim oRouting As RoutingDef
    Do Until oRemove.RoutingIn.Count = 0
        ProcessDef.Routings.Remove oRemove.RoutingIn(1)
    Loop
    Do Until oRemove.RoutingOut.Count = 0
        ProcessDef.Routings.Remove oRemove.RoutingOut(1)
    Loop
End Sub

Public Property Get NewEnum() As IUnknown
Attribute NewEnum.VB_UserMemId = -4
Attribute NewEnum.VB_MemberFlags = "40"
    Set NewEnum = mCol.[_NewEnum]
End Property

Private Sub mContainer_GetMe(oReturn As Object)
    Set oReturn = Me
End Sub

Friend Sub ChangeGUID(oTaskDef As TaskDef, OldGUID As String)
    mCol.Remove OldGUID
    mCol.Add oTaskDef, oTaskDef.GUID
    '# need to alter routings as well
    Dim oRouting As RoutingDef
    For Each oRouting In oTaskDef.RoutingIn
        Set oRouting.TaskDest = oTaskDef
    Next
    For Each oRouting In oTaskDef.RoutingOut
        Set oRouting.TaskOrg = oTaskDef
    Next
End Sub
